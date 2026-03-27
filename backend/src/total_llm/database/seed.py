"""
자동 문서 시드 — 서버 기동 시 data/documents/ 의 파일을 Qdrant + DB에 자동 인덱싱.
이미 등록된 파일명은 건너뜀 (멱등성 보장).
"""
from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
import markdown
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# backend/src/total_llm/database/seed.py → 프로젝트 루트/data/documents
DOCUMENTS_DIR = Path(__file__).resolve().parents[5] / "data" / "documents"


async def seed_documents(
    db_pool: asyncpg.Pool,
    qdrant_service,
    embedding_service,
    settings,
) -> None:
    """data/documents/ 폴더의 .md/.txt 파일을 자동 임베딩·인덱싱한다."""
    if not DOCUMENTS_DIR.exists():
        logger.info("seed: documents directory not found, skipping (%s)", DOCUMENTS_DIR)
        return

    files = sorted(DOCUMENTS_DIR.glob("*.md")) + sorted(DOCUMENTS_DIR.glob("*.txt"))
    if not files:
        logger.info("seed: no documents found in %s", DOCUMENTS_DIR)
        return

    async with db_pool.acquire() as conn:
        existing_rows = await conn.fetch("SELECT filename FROM documents_meta")
    existing_filenames = {row["filename"] for row in existing_rows}

    seeded = 0
    for filepath in files:
        filename = filepath.name
        if filename in existing_filenames:
            logger.debug("seed: skipping already-indexed %s", filename)
            continue

        try:
            raw = filepath.read_bytes()
            suffix = filepath.suffix.lower()
            text = _parse_content(raw, suffix)
            if not text.strip():
                logger.warning("seed: empty content in %s, skipping", filename)
                continue

            chunks = _split_text(text, chunk_size=500, overlap=50)
            if not chunks:
                continue

            # embed_documents 는 async
            vectors = await embedding_service.embed_documents(chunks)

            metadatas = [
                {"filename": filename, "chunk_index": i, "doc_id": None}
                for i in range(len(chunks))
            ]

            # qdrant upsert 는 texts/vectors/metadatas 시그니처
            point_ids = await qdrant_service.upsert(
                texts=chunks,
                vectors=vectors,
                metadatas=metadatas,
            )

            doc_id = point_ids[0] if point_ids else filename

            async with db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO documents_meta (doc_id, filename, size, content_type, chunk_count) "
                    "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
                    doc_id,
                    filename,
                    len(raw),
                    "text/markdown" if suffix in (".md", ".markdown") else "text/plain",
                    len(chunks),
                )

            seeded += 1
            logger.info("seed: indexed %s (%d chunks)", filename, len(chunks))

        except Exception:
            logger.exception("seed: failed to index %s — skipping", filename)

    if seeded:
        logger.info("seed: auto-indexed %d document(s) from %s", seeded, DOCUMENTS_DIR)
    else:
        logger.info("seed: all documents already indexed, nothing to do")


def _parse_content(raw: bytes, suffix: str) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="ignore")

    if suffix in (".md", ".markdown"):
        html = markdown.markdown(text)
        return BeautifulSoup(html, "html.parser").get_text("\n")
    return text


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
