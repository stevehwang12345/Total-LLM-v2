import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from total_llm.models.schemas import ReportModel

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self, report_dir: str = "/app/data/reports/") -> None:
        self._report_dir = Path(report_dir)
        self._report_dir.mkdir(parents=True, exist_ok=True)

    async def generate_report(
        self,
        db_pool: asyncpg.Pool,
        report_type: str,
        params: dict[str, Any],
    ) -> ReportModel:
        report_id = str(uuid4())
        title = f"{report_type.upper()} Report"
        file_path = self._report_dir / f"{report_id}.pdf"

        try:
            self._build_pdf(file_path, title, params)
        except Exception:
            logger.exception("Failed building report PDF: %s", report_id)
            raise

        query = (
            "INSERT INTO reports (report_id, title, file_path) "
            "VALUES ($1, $2, $3) "
            "RETURNING report_id, title, created_at, file_path"
        )

        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, report_id, title, str(file_path))
            if row is None:
                raise RuntimeError("Failed inserting report metadata")
            return self._row_to_model(dict(row))
        except Exception:
            logger.exception("Failed persisting report metadata: %s", report_id)
            raise

    async def list_reports(self, db_pool: asyncpg.Pool) -> list[ReportModel]:
        query = (
            "SELECT report_id, title, created_at, file_path "
            "FROM reports ORDER BY created_at DESC"
        )
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query)
            return [self._row_to_model(dict(row)) for row in rows]
        except Exception:
            logger.exception("Failed listing reports")
            raise

    async def get_report(self, db_pool: asyncpg.Pool, report_id: str) -> ReportModel:
        query = (
            "SELECT report_id, title, created_at, file_path "
            "FROM reports WHERE report_id = $1"
        )
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, report_id)
            if row is None:
                raise ValueError(f"Report not found: {report_id}")
            return self._row_to_model(dict(row))
        except Exception:
            logger.exception("Failed getting report: %s", report_id)
            raise

    async def delete_report(self, db_pool: asyncpg.Pool, report_id: str) -> bool:
        select_query = "SELECT file_path FROM reports WHERE report_id = $1"
        delete_query = "DELETE FROM reports WHERE report_id = $1"

        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(select_query, report_id)
                if row is None:
                    return False
                result = await conn.execute(delete_query, report_id)

            file_path = Path(row["file_path"]) if row["file_path"] else None
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)

            return result.endswith("1")
        except Exception:
            logger.exception("Failed deleting report: %s", report_id)
            raise

    def _build_pdf(self, file_path: Path, title: str, params: dict[str, Any]) -> None:
        c = canvas.Canvas(str(file_path), pagesize=A4)
        width, height = A4

        y = height - 50
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, y, title)

        y -= 30
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Generated at: {datetime.utcnow().isoformat()}Z")

        y -= 25
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Parameters")
        y -= 20

        c.setFont("Helvetica", 10)
        for key, value in params.items():
            line = f"- {key}: {value}"
            c.drawString(60, y, line[:120])
            y -= 16
            if y < 60:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 10)

        c.save()

    def _row_to_model(self, row: dict[str, Any]) -> ReportModel:
        return ReportModel(
            report_id=row["report_id"],
            title=row["title"],
            created_at=row["created_at"],
            download_url=f"/api/reports/{row['report_id']}/download",
        )
