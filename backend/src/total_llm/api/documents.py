from __future__ import annotations

import inspect
import logging
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import asyncpg
import markdown
from bs4 import BeautifulSoup
from docx import Document
from fastapi import APIRouter, Depends, File, Query, UploadFile
from pypdf import PdfReader
from qdrant_client import models as qdrant_models

from ..core.dependencies import (
    get_db_pool,
    get_embedding_service,
    get_qdrant_service,
    get_settings,
)
from ..core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from ..models.schemas import DocumentModel
from ..services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    qdrant_service=Depends(get_qdrant_service),
    embedding_service=Depends(get_embedding_service),
    settings=Depends(get_settings),
):
    if not file.filename:
        raise ValidationError("filename is required")

    raw = await file.read()
    if not raw:
        raise ValidationError("uploaded file is empty")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".md", ".markdown", ".txt"}:
        raise ValidationError("Unsupported file type. Use PDF, DOCX, Markdown, or TXT")

    try:
        text = _parse_file_content(raw=raw, suffix=suffix)
    except Exception as exc:
        logger.exception("Failed parsing document: %s", file.filename)
        raise ValidationError("Failed to parse document") from exc

    if not text.strip():
        raise ValidationError("No extractable text found in document")

    chunks = _split_text(text=text, chunk_size=500, overlap=50)
    if not chunks:
        raise ValidationError("Failed to split document into chunks")

    embedder = embedding_service
    if not hasattr(embedder, "embed_documents"):
        embedder = EmbeddingService()

    try:
        vectors = await _embed_chunks(embedder=embedder, chunks=chunks)
    except Exception as exc:
        logger.exception("Failed embedding document: %s", file.filename)
        raise ExternalServiceError("Embedding failed") from exc

    doc_id = str(uuid4())
    metadatas = [
        {
            "filename": file.filename,
            "chunk_index": index,
            "doc_id": doc_id,
        }
        for index in range(len(chunks))
    ]

    try:
        point_ids = await _upsert_to_qdrant(
            qdrant_service=qdrant_service,
            settings=settings,
            texts=chunks,
            vectors=vectors,
            metadatas=metadatas,
        )
    except Exception as exc:
        logger.exception("Failed upserting vectors for document: %s", file.filename)
        raise ExternalServiceError("Qdrant indexing failed") from exc

    insert_query = (
        "INSERT INTO documents_meta (doc_id, filename, size, content_type, chunk_count) "
        "VALUES ($1, $2, $3, $4, $5)"
    )
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                insert_query,
                doc_id,
                file.filename,
                len(raw),
                file.content_type,
                len(chunks),
            )
    except Exception as exc:
        logger.exception("Failed storing document metadata: %s", doc_id)
        try:
            await _delete_qdrant_by_doc_id(
                qdrant_service=qdrant_service,
                settings=settings,
                doc_id=doc_id,
            )
        except Exception:
            logger.exception("Failed rollback for qdrant points: %s", doc_id)
        raise ExternalServiceError("Failed storing document metadata") from exc

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "size": len(raw),
        "chunk_count": len(chunks),
        "point_ids": point_ids,
    }


@router.get("")
async def list_documents(
    limit: int = Query(default=100, ge=1, le=500),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    query = (
        "SELECT doc_id, filename, size, chunk_count, created_at "
        "FROM documents_meta ORDER BY created_at DESC LIMIT $1"
    )
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
    except Exception as exc:
        logger.exception("Failed listing documents")
        raise ExternalServiceError("Failed listing documents") from exc

    return [DocumentModel.model_validate(dict(row)) for row in rows]


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    qdrant_service=Depends(get_qdrant_service),
    settings=Depends(get_settings),
):
    delete_query = "DELETE FROM documents_meta WHERE doc_id = $1"
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(delete_query, doc_id)
    except Exception as exc:
        logger.exception("Failed deleting document metadata: %s", doc_id)
        raise ExternalServiceError("Failed deleting document metadata") from exc

    if not result.endswith("1"):
        raise NotFoundError("Document not found")

    try:
        await _delete_qdrant_by_doc_id(
            qdrant_service=qdrant_service,
            settings=settings,
            doc_id=doc_id,
        )
    except Exception as exc:
        logger.exception("Failed deleting vectors for document: %s", doc_id)
        raise ExternalServiceError("Failed deleting vectors from Qdrant") from exc

    return {"deleted": True, "doc_id": doc_id}


def _parse_file_content(raw: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if suffix == ".docx":
        doc = Document(BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    text = _decode_text(raw)
    if suffix in {".md", ".markdown"}:
        html = markdown.markdown(text)
        return BeautifulSoup(html, "html.parser").get_text("\n")
    return text


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


async def _embed_chunks(embedder, chunks: list[str]) -> list[list[float]]:
    result = embedder.embed_documents(chunks)
    if inspect.isawaitable(result):
        return await result
    return result


async def _upsert_to_qdrant(
    qdrant_service,
    settings,
    texts: list[str],
    vectors: list[list[float]],
    metadatas: list[dict],
) -> list[str]:
    ensure_collection = getattr(qdrant_service, "ensure_collection", None)
    if callable(ensure_collection):
        maybe = ensure_collection()
        if inspect.isawaitable(maybe):
            await maybe

    if hasattr(qdrant_service, "upsert"):
        try:
            result = qdrant_service.upsert(texts=texts, vectors=vectors, metadatas=metadatas)
            if inspect.isawaitable(result):
                return await result
            return list(result)
        except TypeError:
            pass

        point_ids = [str(uuid4()) for _ in texts]
        points = []
        for index, text in enumerate(texts):
            payload = {"text": text}
            payload.update(metadatas[index])
            points.append(
                qdrant_models.PointStruct(
                    id=point_ids[index],
                    vector=vectors[index],
                    payload=payload,
                )
            )

        result = qdrant_service.upsert(
            collection_name=settings.qdrant.collection_name,
            points=points,
            wait=True,
        )
        if inspect.isawaitable(result):
            await result
        return point_ids

    raise RuntimeError("Qdrant service does not support upsert")


async def _delete_qdrant_by_doc_id(qdrant_service, settings, doc_id: str) -> None:
    if hasattr(qdrant_service, "delete_by_filter"):
        result = qdrant_service.delete_by_filter(key="doc_id", value=doc_id)
        if inspect.isawaitable(result):
            await result
        return

    if hasattr(qdrant_service, "delete"):
        selector = qdrant_models.FilterSelector(
            filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="doc_id",
                        match=qdrant_models.MatchValue(value=doc_id),
                    )
                ]
            )
        )
        result = qdrant_service.delete(
            collection_name=settings.qdrant.collection_name,
            points_selector=selector,
            wait=True,
        )
        if inspect.isawaitable(result):
            await result
        return

    raise RuntimeError("Qdrant service does not support deletion")
