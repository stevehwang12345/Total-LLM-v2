"""LangGraph Agentic RAG with self-correction."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from total_llm.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_QUERY_REWRITES = 2
MIN_RELEVANCE_SCORE = 0.55


class RAGState(TypedDict, total=False):
    query: str
    messages: Annotated[list, add_messages]
    documents: list[dict[str, Any]]
    relevant_documents: list[dict[str, Any]]
    generation: str
    final_response: dict[str, Any]
    query_rewrite_count: int
    relevant_count: int
    route: Literal["simple", "hybrid", "complex"]
    generate_decision: Literal["generate", "transform_query"]
    generation_quality_ok: bool


def create_rag_graph(qdrant_service, embedding_service, llm_client, model_name) -> StateGraph:

    async def classify_query(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        writer = get_stream_writer()

        if not query:
            writer({"event": "classifying", "route": "simple"})
            return {"route": "simple"}

        heuristic_route = _heuristic_route(query)
        route = heuristic_route

        try:
            response = await _chat_json(
                llm_client=llm_client,
                model_name=model_name,
                system_prompt=(
                    "You classify user queries for retrieval complexity. "
                    "Return strict JSON with key route only."
                ),
                user_prompt=(
                    "Choose one route: simple, hybrid, complex.\n"
                    "simple: straightforward factual question\n"
                    "hybrid: requires moderate context synthesis\n"
                    "complex: multi-step reasoning, broad context, or analytical task\n\n"
                    f"Query: {query}\n"
                    "Return JSON: {\"route\":\"simple|hybrid|complex\"}"
                ),
                fallback={"route": heuristic_route},
            )
            route = _coerce_route(response.get("route"), default=heuristic_route)
        except Exception:
            logger.exception("Query classification failed, fallback to heuristic")

        writer({"event": "classifying", "route": route})
        return {"route": route}

    async def retrieve(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        route = _coerce_route(state.get("route"), default="hybrid")
        writer = get_stream_writer()
        writer({"event": "searching", "route": route, "query": query})

        if not query:
            return {"documents": []}

        k_by_route = {"simple": 4, "hybrid": 8, "complex": 12}
        k = k_by_route[route]

        try:
            query_vector = await _embed_query(embedding_service=embedding_service, query=query)
            points = await _search_qdrant(
                qdrant_service=qdrant_service,
                query_vector=query_vector,
                limit=k,
            )
        except Exception:
            logger.exception("RAG retrieval failed")
            points = []

        documents = [_normalize_document(point) for point in points]
        documents = [doc for doc in documents if doc.get("text")]

        writer({"event": "search_completed", "count": len(documents)})
        return {"documents": documents}

    async def grade_documents(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        documents = state.get("documents") or []
        writer = get_stream_writer()
        writer({"event": "grading_documents", "count": len(documents)})

        if not query or not documents:
            return {"relevant_documents": [], "relevant_count": 0}

        scored_documents: list[dict[str, Any]] = []
        for document in documents:
            text = str(document.get("text") or "").strip()
            if not text:
                continue

            score = await _grade_document_relevance(
                llm_client=llm_client,
                model_name=model_name,
                query=query,
                document_text=text,
            )

            enriched = dict(document)
            enriched["relevance_score"] = score
            scored_documents.append(enriched)

        scored_documents.sort(key=lambda item: item.get("relevance_score", 0.0), reverse=True)
        relevant_documents = [
            item for item in scored_documents if float(item.get("relevance_score", 0.0)) >= MIN_RELEVANCE_SCORE
        ]

        writer(
            {
                "event": "grading_completed",
                "total": len(scored_documents),
                "relevant": len(relevant_documents),
            }
        )
        return {
            "documents": scored_documents,
            "relevant_documents": relevant_documents,
            "relevant_count": len(relevant_documents),
        }

    async def decide_to_generate(state: RAGState) -> dict[str, Any]:
        route = _coerce_route(state.get("route"), default="hybrid")
        relevant_documents = state.get("relevant_documents") or []
        rewrite_count = int(state.get("query_rewrite_count", 0))
        writer = get_stream_writer()

        threshold_by_route = {"simple": 1, "hybrid": 2, "complex": 3}
        threshold = threshold_by_route[route]

        enough_docs = len(relevant_documents) >= threshold
        if enough_docs or rewrite_count >= MAX_QUERY_REWRITES:
            decision: Literal["generate", "transform_query"] = "generate"
        else:
            decision = "transform_query"

        writer(
            {
                "event": "decision",
                "decision": decision,
                "relevant": len(relevant_documents),
                "threshold": threshold,
                "rewrite_count": rewrite_count,
            }
        )
        return {"generate_decision": decision}

    async def transform_query(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        rewrite_count = int(state.get("query_rewrite_count", 0))
        writer = get_stream_writer()

        if rewrite_count >= MAX_QUERY_REWRITES:
            writer({"event": "rewrite_skipped", "reason": "max_rewrites_reached"})
            return {}

        relevant_documents = state.get("relevant_documents") or []
        generation = (state.get("generation") or "").strip()

        reason = "insufficient_retrieval" if not generation else "generation_quality"
        candidate_context = "\n\n".join(
            f"- {str(doc.get('text', ''))[:220]}" for doc in relevant_documents[:3]
        )

        rewritten = query
        try:
            response = await _chat_json(
                llm_client=llm_client,
                model_name=model_name,
                system_prompt=(
                    "You rewrite search queries to improve retrieval quality while preserving intent. "
                    "Return strict JSON only."
                ),
                user_prompt=(
                    f"Original query: {query}\n"
                    f"Reason: {reason}\n"
                    f"Current snippets:\n{candidate_context or '- none -'}\n"
                    "Rewrite for clearer entities, constraints, and intent."
                    " Keep it concise.\n"
                    "Return JSON: {\"rewritten_query\":\"...\"}"
                ),
                fallback={"rewritten_query": query},
            )
            rewritten = str(response.get("rewritten_query") or query).strip() or query
        except Exception:
            logger.exception("Query rewrite failed, keeping original query")

        next_rewrite_count = rewrite_count + (1 if rewritten else 0)
        writer(
            {
                "event": "rewriting",
                "rewrite_count": next_rewrite_count,
                "query": rewritten,
            }
        )
        return {
            "query": rewritten,
            "query_rewrite_count": next_rewrite_count,
        }

    async def generate(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        relevant_documents = state.get("relevant_documents") or []
        writer = get_stream_writer()
        writer({"event": "generating", "doc_count": len(relevant_documents)})

        context_blocks = []
        for idx, doc in enumerate(relevant_documents[:8], start=1):
            text = str(doc.get("text") or "").strip()
            if not text:
                continue
            metadata = doc.get("metadata") or {}
            source_name = metadata.get("filename") or metadata.get("source") or f"doc_{idx}"
            context_blocks.append(f"[source:{source_name}]\n{text}")

        context_text = "\n\n".join(context_blocks)
        user_prompt = (
            "Answer the user question using only the retrieved context.\n"
            "If information is insufficient, state exactly what is missing.\n"
            "Cite source tags like [source:...].\n\n"
            f"Question: {query}\n\n"
            f"Retrieved context:\n{context_text or 'No context available.'}"
        )

        generation_parts: list[str] = []
        try:
            stream = await llm_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a careful RAG assistant. Provide grounded answers only."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = (delta.content or "") if delta else ""
                if not token:
                    continue
                generation_parts.append(token)
                writer({"event": "token", "content": token})
        except Exception:
            logger.exception("Streaming generation failed; fallback to non-stream call")
            fallback = await llm_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a careful RAG assistant. Provide grounded answers only.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            text = ""
            if fallback.choices:
                text = (fallback.choices[0].message.content or "").strip()
            if text:
                generation_parts.append(text)
                writer({"event": "token", "content": text})

        generation = "".join(generation_parts).strip()
        return {
            "generation": generation,
            "messages": [{"role": "assistant", "content": generation}],
        }

    async def grade_generation(state: RAGState) -> dict[str, Any]:
        query = (state.get("query") or "").strip()
        generation = (state.get("generation") or "").strip()
        relevant_documents = state.get("relevant_documents") or []
        rewrite_count = int(state.get("query_rewrite_count", 0))
        writer = get_stream_writer()

        if not generation:
            writer({"event": "grade_generation", "ok": False, "reason": "empty_generation"})
            return {"generation_quality_ok": False}

        context_text = "\n\n".join(str(doc.get("text") or "")[:700] for doc in relevant_documents[:5])
        fallback_ok = bool(relevant_documents) or rewrite_count >= MAX_QUERY_REWRITES

        ok = fallback_ok
        try:
            result = await _chat_json(
                llm_client=llm_client,
                model_name=model_name,
                system_prompt=(
                    "You are a strict evaluator for grounded RAG answers. "
                    "Return strict JSON only."
                ),
                user_prompt=(
                    f"User query:\n{query}\n\n"
                    f"Retrieved evidence:\n{context_text or '- none -'}\n\n"
                    f"Assistant answer:\n{generation}\n\n"
                    "Evaluate groundedness and usefulness.\n"
                    "Return JSON: {\"grounded\":true|false,\"helpful\":true|false,\"score\":0..1,\"reason\":\"...\"}"
                ),
                fallback={
                    "grounded": fallback_ok,
                    "helpful": bool(generation),
                    "score": 0.7 if fallback_ok else 0.4,
                },
            )
            grounded = bool(result.get("grounded"))
            helpful = bool(result.get("helpful"))
            score = _safe_float(result.get("score"), default=0.0)
            ok = grounded and helpful and score >= 0.6
        except Exception:
            logger.exception("Generation grading failed, fallback to heuristic")

        if rewrite_count >= MAX_QUERY_REWRITES:
            ok = True

        writer({"event": "grade_generation", "ok": ok, "rewrite_count": rewrite_count})
        return {"generation_quality_ok": ok}

    async def output(state: RAGState) -> dict[str, Any]:
        generation = (state.get("generation") or "").strip()
        relevant_documents = state.get("relevant_documents") or []

        sources = []
        for doc in relevant_documents:
            metadata = dict(doc.get("metadata") or {})
            source = {
                "filename": metadata.get("filename"),
                "doc_id": metadata.get("doc_id"),
                "chunk_index": metadata.get("chunk_index"),
                "score": doc.get("relevance_score", doc.get("score")),
            }
            sources.append(source)

        final_response = {
            "answer": generation,
            "route": _coerce_route(state.get("route"), default="hybrid"),
            "rewrite_count": int(state.get("query_rewrite_count", 0)),
            "sources": sources,
        }
        get_stream_writer()(
            {
                "event": "completed",
                "source_count": len(sources),
            }
        )
        return {"final_response": final_response}

    graph = StateGraph(RAGState)
    graph.add_node("classify_query", classify_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_documents", grade_documents)
    graph.add_node("decide_to_generate", decide_to_generate)
    graph.add_node("transform_query", transform_query)
    graph.add_node("generate", generate)
    graph.add_node("grade_generation", grade_generation)
    graph.add_node("output", output)

    graph.add_edge(START, "classify_query")
    graph.add_edge("classify_query", "retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_edge("grade_documents", "decide_to_generate")
    graph.add_conditional_edges(
        "decide_to_generate",
        _decide_generation_route,
        {
            "generate": "generate",
            "transform_query": "transform_query",
        },
    )
    graph.add_edge("transform_query", "retrieve")
    graph.add_edge("generate", "grade_generation")
    graph.add_conditional_edges(
        "grade_generation",
        _decide_output_route,
        {
            "output": "output",
            "transform_query": "transform_query",
        },
    )
    graph.add_edge("output", END)

    return cast(StateGraph, graph.compile())


async def stream_rag_response(graph, query: str, conversation_id: str | None = None):
    conv_id = conversation_id or str(uuid4())

    initial_state: RAGState = {
        "query": query,
        "messages": [{"role": "user", "content": query}],
        "documents": [],
        "generation": "",
        "query_rewrite_count": 0,
        "route": "hybrid",
    }

    yield {"conversation_id": conv_id}

    token_emitted = False
    final_response: dict[str, Any] | None = None

    async for event in graph.astream(
        initial_state,
        stream_mode=["custom", "updates"],
    ):
        if isinstance(event, tuple):
            mode, payload = event
        else:
            mode, payload = "updates", event

        if mode == "custom" and isinstance(payload, dict):
            event_name = payload.get("event")

            if event_name == "token":
                token = str(payload.get("content") or "")
                if token:
                    token_emitted = True
                    yield {"content": token}
                continue

            if event_name in {"searching", "grading_documents", "generating", "rewriting"}:
                yield {
                    "event": event_name,
                    **{key: value for key, value in payload.items() if key != "event"},
                }

        if mode == "updates" and isinstance(payload, dict):
            output_state = payload.get("output")
            if output_state and isinstance(output_state, dict):
                maybe_final = output_state.get("final_response")
                if isinstance(maybe_final, dict):
                    final_response = maybe_final

    if final_response and not token_emitted:
        answer = str(final_response.get("answer") or "")
        if answer:
            yield {"content": answer}

    yield {
        "done": True,
        "conversation_id": conv_id,
        "result": final_response or {},
    }


def _decide_generation_route(state: RAGState) -> str:
    return state.get("generate_decision", "generate")


def _decide_output_route(state: RAGState) -> str:
    rewrite_count = int(state.get("query_rewrite_count", 0))
    quality_ok = bool(state.get("generation_quality_ok"))
    if quality_ok or rewrite_count >= MAX_QUERY_REWRITES:
        return "output"
    return "transform_query"


def _heuristic_route(query: str) -> Literal["simple", "hybrid", "complex"]:
    lowered = query.lower()
    complex_markers = [
        "why",
        "how",
        "compare",
        "trade-off",
        "analyze",
        "분석",
        "원인",
        "전략",
    ]
    if any(marker in lowered for marker in complex_markers):
        return "complex"

    word_count = len(query.split())
    if word_count <= 6:
        return "simple"
    if word_count <= 18:
        return "hybrid"
    return "complex"


def _coerce_route(value: Any, default: Literal["simple", "hybrid", "complex"] = "hybrid") -> Literal["simple", "hybrid", "complex"]:
    normalized = str(value or "").strip().lower()
    if normalized in {"simple", "hybrid", "complex"}:
        return normalized  # type: ignore[return-value]
    return default


async def _embed_query(embedding_service, query: str) -> list[float]:
    if hasattr(embedding_service, "embed_query"):
        result = embedding_service.embed_query(query)
        if inspect.isawaitable(result):
            return await result
        return result
    raise RuntimeError("Embedding service does not support embed_query")


async def _search_qdrant(
    qdrant_service,
    query_vector: list[float],
    limit: int,
) -> list[Any]:
    if not hasattr(qdrant_service, "search"):
        raise RuntimeError("Qdrant service does not support search")

    search_callable = qdrant_service.search
    try:
        search_result = search_callable(query_vector=query_vector, limit=limit)
    except TypeError:
        settings = get_settings()
        search_result = search_callable(
            collection_name=settings.qdrant.collection_name,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

    if inspect.isawaitable(search_result):
        return await search_result
    return list(search_result)


def _normalize_document(point: Any) -> dict[str, Any]:
    payload = getattr(point, "payload", None)
    if payload is None and isinstance(point, dict):
        payload = point.get("payload", {})
    payload = payload or {}

    text = str(payload.get("text") or payload.get("content") or "").strip()

    score_value = getattr(point, "score", None)
    if score_value is None and isinstance(point, dict):
        score_value = point.get("score")

    metadata = {key: value for key, value in payload.items() if key not in {"text", "content"}}
    return {
        "text": text,
        "score": _safe_float(score_value, default=0.0),
        "metadata": metadata,
    }


async def _grade_document_relevance(
    llm_client,
    model_name: str,
    query: str,
    document_text: str,
) -> float:
    if llm_client is None:
        return _keyword_overlap_score(query, document_text)

    fallback_score = _keyword_overlap_score(query, document_text)
    response = await _chat_json(
        llm_client=llm_client,
        model_name=model_name,
        system_prompt=(
            "You score relevance between query and candidate document chunk. "
            "Return strict JSON only."
        ),
        user_prompt=(
            f"Query:\n{query}\n\n"
            f"Document:\n{document_text[:1800]}\n\n"
            "Return JSON: {\"score\":0..1,\"relevant\":true|false,\"reason\":\"...\"}"
        ),
        fallback={"score": fallback_score, "relevant": fallback_score >= MIN_RELEVANCE_SCORE},
    )
    score = _safe_float(response.get("score"), default=fallback_score)
    return max(0.0, min(1.0, score))


def _keyword_overlap_score(query: str, text: str) -> float:
    query_tokens = {token for token in _tokenize(query) if len(token) > 2}
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokenize(text))
    overlap = len(query_tokens & text_tokens)
    return max(0.0, min(1.0, overlap / max(1, len(query_tokens))))


def _tokenize(value: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return [token for token in cleaned.split() if token]


async def _chat_json(
    llm_client,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if llm_client is None:
        return fallback

    kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }

    content = ""
    try:
        completion = await llm_client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
        if completion.choices:
            content = completion.choices[0].message.content or ""
    except Exception:
        completion = await llm_client.chat.completions.create(**kwargs)
        if completion.choices:
            content = completion.choices[0].message.content or ""

    parsed = _parse_json(content)
    if not parsed:
        return fallback
    merged = dict(fallback)
    merged.update(parsed)
    return merged


def _parse_json(value: str) -> dict[str, Any]:
    raw = (value or "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    try:
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}

    return {}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
