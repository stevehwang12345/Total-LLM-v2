import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import cm

from total_llm.models.schemas import ReportModel

logger = logging.getLogger(__name__)

_KOREAN_FONTS_REGISTERED = False
REPORT_TYPE_MAP = {
    "daily_log": "_build_daily_log_pdf",
    "incident": "_build_incident_report_pdf",
    "equipment": "_build_equipment_report_pdf",
    "monthly": "_build_monthly_report_pdf",
}


def register_korean_fonts() -> str:
    """NanumGothic 폰트를 ReportLab에 등록. 등록된 폰트 이름 반환."""
    global _KOREAN_FONTS_REGISTERED
    if _KOREAN_FONTS_REGISTERED:
        return "NanumGothic"
    
    font_paths = {
        "NanumGothic": [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/nanum/NanumGothic.ttf",
        ],
        "NanumGothicBold": [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/nanum/NanumGothicBold.ttf",
        ],
    }
    
    registered = []
    for font_name, paths in font_paths.items():
        for path in paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(font_name, path))
                registered.append(font_name)
                break
    
    if "NanumGothic" in registered and "NanumGothicBold" in registered:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            "NanumGothic",
            normal="NanumGothic",
            bold="NanumGothicBold",
            italic="NanumGothic",
            boldItalic="NanumGothicBold",
        )
        _KOREAN_FONTS_REGISTERED = True
        return "NanumGothic"
    
    # Fallback to Helvetica (non-Korean environments)
    logger.warning("NanumGothic font not found; falling back to Helvetica")
    return "Helvetica"


def get_korean_styles(base_font: str = "NanumGothic") -> dict:
    """보안 보고서용 한글 ParagraphStyle 사전 반환."""
    bold = f"{base_font}{'Bold' if base_font == 'NanumGothic' else '-Bold'}"
    return {
        "title": ParagraphStyle(
            "KorTitle", fontName=bold, fontSize=16, leading=22, alignment=TA_CENTER, spaceAfter=12
        ),
        "heading1": ParagraphStyle(
            "KorH1", fontName=bold, fontSize=13, leading=18, spaceBefore=10, spaceAfter=6
        ),
        "heading2": ParagraphStyle(
            "KorH2", fontName=bold, fontSize=11, leading=16, spaceBefore=8, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "KorBody", fontName=base_font, fontSize=9, leading=14, wordWrap="CJK"
        ),
        "table_header": ParagraphStyle(
            "KorTH", fontName=bold, fontSize=9, leading=12, alignment=TA_CENTER
        ),
        "table_cell": ParagraphStyle(
            "KorTC", fontName=base_font, fontSize=8, leading=11, wordWrap="CJK"
        ),
        "footer": ParagraphStyle(
            "KorFooter", fontName=base_font, fontSize=7, leading=10, alignment=TA_CENTER, textColor=colors.grey
        ),
    }



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
        type_label = {
            "daily_log": "관제일지",
            "incident": "사건보고서",
            "equipment": "장비점검일지",
            "monthly": "월간보안보고서",
        }.get(report_type, report_type.upper())
        title = f"{type_label} ({params.get('date', params.get('year', ''))})"
        file_path = self._report_dir / f"{report_id}.pdf"

        try:
            if report_type == "daily_log":
                data = await self.aggregate_daily_log(
                    db_pool,
                    params.get("date", str(datetime.utcnow().date())),
                )
                self._build_daily_log_pdf(file_path, data)
            elif report_type == "incident":
                data = await self.aggregate_incident_report(
                    db_pool,
                    params.get("alarm_id", ""),
                )
                self._build_incident_report_pdf(file_path, data)
            elif report_type == "equipment":
                data = await self.aggregate_equipment_report(
                    db_pool,
                    params.get("date", str(datetime.utcnow().date())),
                )
                self._build_equipment_report_pdf(file_path, data)
            elif report_type == "monthly":
                data = await self.aggregate_monthly_report(
                    db_pool,
                    int(params.get("year", datetime.utcnow().year)),
                    int(params.get("month", datetime.utcnow().month)),
                )
                self._build_monthly_report_pdf(file_path, data)
            else:
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas as cv

                c = cv.Canvas(str(file_path), pagesize=A4)
                _, height = A4
                c.setFont("Helvetica-Bold", 14)
                c.drawString(50, height - 50, f"{report_type.upper()} Report")
                c.setFont("Helvetica", 10)
                y = height - 80
                for key, value in params.items():
                    c.drawString(60, y, f"{key}: {value}")
                    y -= 16
                c.save()
        except Exception:
            logger.exception("Failed building report PDF: %s", report_id)
            raise

        query = (
            "INSERT INTO reports (report_id, title, report_type, file_path) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING report_id, title, report_type, created_at, file_path"
        )

        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, report_id, title, report_type, str(file_path))
            if row is None:
                raise RuntimeError("Failed inserting report metadata")
            return self._row_to_model(dict(row))
        except Exception:
            logger.exception("Failed persisting report metadata: %s", report_id)
            raise

    async def list_reports(self, db_pool: asyncpg.Pool) -> list[ReportModel]:
        query = (
            "SELECT report_id, title, report_type, created_at, file_path "
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
            "SELECT report_id, title, report_type, created_at, file_path "
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

    async def aggregate_daily_log(
        self,
        db_pool: asyncpg.Pool,
        target_date: str,
    ) -> dict[str, Any]:
        from datetime import date as date_type
        date_obj = date_type.fromisoformat(target_date)
        async with db_pool.acquire() as conn:
            alarm_stats = await conn.fetchrow(
                "SELECT COUNT(*) as total, "
                "COUNT(*) FILTER (WHERE status = 'closed') as closed_count, "
                "COUNT(*) FILTER (WHERE status NOT IN ('closed','false_alarm')) as open_count, "
                "COUNT(*) FILTER (WHERE status = 'false_alarm') as false_alarm_count "
                "FROM alarms WHERE DATE(timestamp) = $1",
                date_obj,
            )
            device_stats = await conn.fetchrow(
                "SELECT COUNT(*) as total, "
                "COUNT(*) FILTER (WHERE status = 'online') as online_count, "
                "COUNT(*) FILTER (WHERE status = 'offline') as offline_count "
                "FROM devices",
            )
            severity_rows = await conn.fetch(
                "SELECT severity, COUNT(*) as count FROM alarms "
                "WHERE DATE(timestamp) = $1 GROUP BY severity",
                date_obj,
            )

        return {
            "date": target_date,
            "alarms": dict(alarm_stats) if alarm_stats else {},
            "devices": dict(device_stats) if device_stats else {},
            "alarms_by_severity": {row["severity"]: row["count"] for row in severity_rows},
        }

    async def aggregate_incident_report(
        self,
        db_pool: asyncpg.Pool,
        alarm_id: str,
    ) -> dict[str, Any]:
        async with db_pool.acquire() as conn:
            alarm_row = await conn.fetchrow(
                "SELECT a.alarm_id, a.device_id, a.severity, a.description, "
                "a.timestamp, a.status, a.priority, a.analysis_id, "
                "a.resolved_at, a.resolved_by, a.investigation_notes, "
                "d.location, d.device_type, d.manufacturer "
                "FROM alarms a "
                "LEFT JOIN devices d ON a.device_id = d.device_id "
                "WHERE a.alarm_id = $1",
                alarm_id,
            )
            analysis_row = None
            if alarm_row and alarm_row["analysis_id"]:
                analysis_row = await conn.fetchrow(
                    "SELECT analysis_id, location, result, media_type, created_at "
                    "FROM analyses WHERE analysis_id = $1",
                    alarm_row["analysis_id"],
                )

        if not alarm_row:
            return {}

        result = dict(alarm_row)
        result["analysis"] = dict(analysis_row) if analysis_row else None
        return result

    async def aggregate_equipment_report(
        self,
        db_pool: asyncpg.Pool,
        target_date: str,
    ) -> dict[str, Any]:
        from datetime import date as date_type
        date_obj = date_type.fromisoformat(target_date)
        async with db_pool.acquire() as conn:
            device_rows = await conn.fetch(
                "SELECT device_id, device_type, manufacturer, ip_address, port, "
                "protocol, location, status, security_grade, firmware_version, last_health_check "
                "FROM devices ORDER BY device_type, device_id",
            )
            health_rows = await conn.fetch(
                "SELECT dhl.device_id, dhl.checked_at, dhl.reachable, dhl.port_open, "
                "dhl.latency_ms, dhl.status "
                "FROM device_health_logs dhl "
                "WHERE DATE(dhl.checked_at) = $1 "
                "ORDER BY dhl.device_id, dhl.checked_at DESC",
                date_obj,
            )

        health_by_device: dict[str, list[dict[str, Any]]] = {}
        for row in health_rows:
            device_id = row["device_id"]
            health_by_device.setdefault(device_id, []).append(dict(row))

        devices = []
        for row in device_rows:
            device = dict(row)
            device["health_logs"] = health_by_device.get(device["device_id"], [])
            devices.append(device)

        return {
            "date": target_date,
            "devices": devices,
            "total": len(devices),
            "online": sum(1 for device in devices if device["status"] == "online"),
            "offline": sum(1 for device in devices if device["status"] == "offline"),
        }

    async def aggregate_monthly_report(
        self,
        db_pool: asyncpg.Pool,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        from datetime import date as date_type
        period_start_str = f"{year:04d}-{month:02d}-01"
        period_end_str = (
            f"{year:04d}-{month + 1:02d}-01"
            if month < 12
            else f"{year + 1:04d}-01-01"
        )
        period_start = date_type.fromisoformat(period_start_str)
        period_end = date_type.fromisoformat(period_end_str)

        async with db_pool.acquire() as conn:
            alarm_total = await conn.fetchval(
                "SELECT COUNT(*) FROM alarms WHERE timestamp >= $1 AND timestamp < $2",
                period_start,
                period_end,
            )
            false_alarm_count = await conn.fetchval(
                "SELECT COUNT(*) FROM alarms WHERE status = 'false_alarm' AND timestamp >= $1 AND timestamp < $2",
                period_start,
                period_end,
            )
            severity_rows = await conn.fetch(
                "SELECT severity, COUNT(*) as count FROM alarms "
                "WHERE timestamp >= $1 AND timestamp < $2 GROUP BY severity",
                period_start,
                period_end,
            )
            daily_rows = await conn.fetch(
                "SELECT DATE(timestamp) as day, COUNT(*) as count FROM alarms "
                "WHERE timestamp >= $1 AND timestamp < $2 GROUP BY DATE(timestamp) ORDER BY day",
                period_start,
                period_end,
            )
            analysis_count = await conn.fetchval(
                "SELECT COUNT(*) FROM analyses WHERE created_at >= $1 AND created_at < $2",
                period_start,
                period_end,
            )
            high_risk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM analyses "
                "WHERE (result->>'risk_level')::int >= 3 "
                "AND created_at >= $1 AND created_at < $2",
                period_start,
                period_end,
            )
            device_count = await conn.fetchval("SELECT COUNT(*) FROM devices")
            online_count = await conn.fetchval("SELECT COUNT(*) FROM devices WHERE status = 'online'")

        safe_alarm_total = alarm_total or 0
        safe_false_alarm_count = false_alarm_count or 0
        safe_analysis_count = analysis_count or 0
        safe_high_risk_count = high_risk_count or 0
        safe_device_count = device_count or 0
        safe_online_count = online_count or 0

        return {
            "period": {
                "year": year,
                "month": month,
                "start": period_start,
                "end": period_end,
            },
            "alarms": {
                "total": safe_alarm_total,
                "false_alarm_count": safe_false_alarm_count,
                "false_alarm_rate": round(safe_false_alarm_count / max(safe_alarm_total, 1) * 100, 1),
                "by_severity": {row["severity"]: row["count"] for row in severity_rows},
                "daily_trend": [{"date": str(row["day"]), "count": row["count"]} for row in daily_rows],
            },
            "analyses": {
                "total": safe_analysis_count,
                "high_risk_count": safe_high_risk_count,
            },
            "devices": {
                "total": safe_device_count,
                "online": safe_online_count,
                "availability_rate": round(safe_online_count / max(safe_device_count, 1) * 100, 1),
            },
        }

    def _build_daily_log_pdf(self, file_path: Path, data: dict) -> None:
        font = register_korean_fonts()
        styles = get_korean_styles(font)
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        story = []

        story.append(Paragraph("보안관제 근무일지 (관제일지)", styles["title"]))
        story.append(Spacer(1, 0.3 * cm))

        date_str = data.get("date", "")
        info_data = [["일자", date_str, "보안등급", "대외비"]]
        info_table = Table(info_data, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
        info_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8edf2")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8edf2")),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(info_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("■ 알람 발생 현황", styles["heading1"]))
        alarms = data.get("alarms", {})
        alarm_data = [
            ["총 발생", "처리 완료", "미처리", "오경보"],
            [
                str(alarms.get("total", 0)),
                str(alarms.get("closed_count", 0)),
                str(alarms.get("open_count", 0)),
                str(alarms.get("false_alarm_count", 0)),
            ],
        ]
        alarm_table = Table(alarm_data, colWidths=[4.25 * cm] * 4)
        alarm_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(alarm_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("■ 장비 운영 현황", styles["heading1"]))
        devices = data.get("devices", {})
        dev_data = [
            ["총 장비", "정상", "장애"],
            [
                str(devices.get("total", 0)),
                str(devices.get("online_count", 0)),
                str(devices.get("offline_count", 0)),
            ],
        ]
        dev_table = Table(dev_data, colWidths=[5.66 * cm] * 3)
        dev_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(dev_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("■ 특이사항 및 인수인계", styles["heading1"]))
        story.append(Paragraph(data.get("notes", "해당 없음"), styles["body"]))
        story.append(Spacer(1, 0.5 * cm))

        sign_data = [["작성자", "", "확인자", "", "결재", ""]]
        sign_table = Table(
            sign_data,
            colWidths=[2.5 * cm, 4 * cm, 2.5 * cm, 4 * cm, 2 * cm, 2 * cm],
        )
        sign_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8edf2")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8edf2")),
                    ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#e8edf2")),
                    ("MINROWHEIGHT", (0, 0), (-1, -1), 1.5 * cm),
                ]
            )
        )
        story.append(sign_table)

        doc.build(story)

    def _build_incident_report_pdf(self, file_path: Path, data: dict) -> None:
        font = register_korean_fonts()
        styles = get_korean_styles(font)
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        story = []
        story.append(Paragraph("보안사건 발생보고 (사건보고서)", styles["title"]))

        header_data = [["문서번호", f"IR-{data.get('alarm_id', '')[:12]}", "보안등급", "대외비"]]
        h_table = Table(header_data, colWidths=[3 * cm, 7 * cm, 3 * cm, 4 * cm])
        h_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8edf2")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8edf2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(h_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("1. 사건 개요", styles["heading1"]))
        overview_data = [
            ["사건 유형", data.get("severity", ""), "우선순위", data.get("priority", "")],
            ["발생 일시", str(data.get("timestamp", "")), "발생 장소", data.get("location", "미상")],
            ["사건 상태", data.get("status", ""), "장비 ID", data.get("device_id", "")],
        ]
        ov_table = Table(overview_data, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
        ov_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8edf2")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8edf2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(ov_table)
        story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph("2. 사건 내용", styles["heading1"]))
        story.append(Paragraph(data.get("description", "상세 내용 없음"), styles["body"]))
        story.append(Spacer(1, 0.3 * cm))

        analysis = data.get("analysis")
        if analysis:
            story.append(Paragraph("3. AI 영상분석 결과", styles["heading1"]))
            result = analysis.get("result", {})
            story.append(Paragraph(f"사건 유형: {result.get('incident_type', '')}", styles["body"]))
            story.append(
                Paragraph(
                    f"위험도: {result.get('risk_level', '')} ({result.get('severity', '')})",
                    styles["body"],
                )
            )
            story.append(Paragraph(f"신뢰도: {result.get('confidence', '')}", styles["body"]))
            story.append(Spacer(1, 0.2 * cm))

        story.append(Paragraph("4. 초동 조치 및 대응", styles["heading1"]))
        story.append(Paragraph(data.get("investigation_notes", "기록 없음"), styles["body"]))

        doc.build(story)

    def _build_equipment_report_pdf(self, file_path: Path, data: dict) -> None:
        font = register_korean_fonts()
        styles = get_korean_styles(font)
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        story = []
        story.append(Paragraph("보안장비 정기점검 기록부 (장비점검일지)", styles["title"]))
        story.append(Paragraph(f"점검일자: {data.get('date', '')}", styles["body"]))
        story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph("■ 장비 현황 요약", styles["heading1"]))
        summary_data = [
            ["총 장비", "정상 (온라인)", "장애 (오프라인)"],
            [str(data.get("total", 0)), str(data.get("online", 0)), str(data.get("offline", 0))],
        ]
        s_table = Table(summary_data, colWidths=[5.66 * cm] * 3)
        s_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(s_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("■ 장비 점검 목록", styles["heading1"]))
        header = ["장비ID", "유형", "위치", "상태", "보안등급", "최종점검"]
        dev_rows = [header]
        for dev in data.get("devices", [])[:50]:
            dev_rows.append(
                [
                    dev.get("device_id", ""),
                    dev.get("device_type", ""),
                    dev.get("location", ""),
                    dev.get("status", ""),
                    dev.get("security_grade", ""),
                    str(dev.get("last_health_check", ""))[:16]
                    if dev.get("last_health_check")
                    else "미점검",
                ]
            )
        dev_table = Table(dev_rows, colWidths=[3 * cm, 2 * cm, 3.5 * cm, 2 * cm, 2.5 * cm, 3.5 * cm])
        dev_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                ]
            )
        )
        story.append(dev_table)

        doc.build(story)

    def _build_monthly_report_pdf(self, file_path: Path, data: dict) -> None:
        font = register_korean_fonts()
        styles = get_korean_styles(font)
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        period = data.get("period", {})
        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        story = []
        story.append(
            Paragraph(
                f"월간 보안 현황 보고서 ({period.get('year', '')}년 {period.get('month', '')}월)",
                styles["title"],
            )
        )
        story.append(Paragraph("보안등급: 대외비", styles["body"]))
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph("1. 알람 발생 현황", styles["heading1"]))
        alarms = data.get("alarms", {})
        alarm_data = [
            ["총 알람", "오경보", "오경보율", "일평균"],
            [
                str(alarms.get("total", 0)),
                str(alarms.get("false_alarm_count", 0)),
                f"{alarms.get('false_alarm_rate', 0):.1f}%",
                f"{alarms.get('total', 0) / 30:.1f}",
            ],
        ]
        a_table = Table(alarm_data, colWidths=[4.25 * cm] * 4)
        a_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(a_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("2. AI 영상분석 현황", styles["heading1"]))
        analyses = data.get("analyses", {})
        an_data = [
            ["총 분석", "고위험(3+)", "고위험 비율"],
            [
                str(analyses.get("total", 0)),
                str(analyses.get("high_risk_count", 0)),
                f"{analyses.get('high_risk_count', 0) / max(analyses.get('total', 1), 1) * 100:.1f}%",
            ],
        ]
        an_table = Table(an_data, colWidths=[5.66 * cm] * 3)
        an_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(an_table)
        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph("3. 장비 운영 현황", styles["heading1"]))
        devs = data.get("devices", {})
        d_data = [
            ["총 장비", "온라인", "가용성"],
            [
                str(devs.get("total", 0)),
                str(devs.get("online", 0)),
                f"{devs.get('availability_rate', 0):.1f}%",
            ],
        ]
        d_table = Table(d_data, colWidths=[5.66 * cm] * 3)
        d_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(d_table)

        doc.build(story)

    def _row_to_model(self, row: dict[str, Any]) -> ReportModel:
        return ReportModel(
            report_id=row["report_id"],
            title=row["title"],
            type=row.get("report_type", "security"),
            created_at=row["created_at"],
            download_url=f"/api/reports/{row['report_id']}/download",
        )
