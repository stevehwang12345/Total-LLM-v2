import asyncio
import logging
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from total_llm.core.config import get_settings
from total_llm.models import schemas as schema_models

logger = logging.getLogger(__name__)

IncidentAnalysis = getattr(schema_models, "IncidentAnalysis", schema_models.AnalysisResult)


class VLMService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def analyze_image(
        self,
        client: AsyncOpenAI,
        image_base64: str,
        location: str | None = None,
        timestamp: datetime | None = None,
    ) -> Any:
        if not image_base64 or not image_base64.strip():
            raise ValueError("image_base64 cannot be empty")

        questions = [
            "이 이미지에서 폭력, 범죄, 위험한 상황이 보이나요?",
            "감지된 사건의 유형을 분류해주세요",
            "관련된 인물이나 객체를 설명해주세요",
            "전체 상황을 상세히 설명해주세요",
        ]

        context = self._build_context(location=location, timestamp=timestamp)

        q1, q2, q3, q4 = await asyncio.gather(
            self._ask_question(client, image_base64, questions[0], context),
            self._ask_question(client, image_base64, questions[1], context),
            self._ask_question(client, image_base64, questions[2], context),
            self._ask_question(client, image_base64, questions[3], context),
        )

        qa_results = {
            "q1_safety_risk": q1,
            "q2_incident_type": q2,
            "q3_entities": q3,
            "q4_situation": q4,
        }
        incident_type = self._normalize_incident_type(q2)
        severity = self._infer_severity(q1, q2)
        confidence = self._infer_confidence(q1, q2, q3, q4)
        report = self._compose_report(location, timestamp, q1, q2, q3, q4)

        payload: dict[str, Any] = {
            "qa_results": qa_results,
            "incident_type": incident_type,
            "severity": severity,
            "confidence": confidence,
            "report": report,
            "location": location,
            "timestamp": timestamp,
            "summary": report,
            "analysis": report,
            "description": report,
        }

        return self._build_incident_model(payload)

    async def _ask_question(
        self,
        client: AsyncOpenAI,
        image_base64: str,
        question: str,
        context: str,
    ) -> str:
        prompt = (
            "당신은 산업/보안 관제 분석가입니다. "
            "이미지를 보고 사실 기반으로 답변하세요. "
            "불확실하면 불확실하다고 명시하세요.\n"
            f"{context}\n"
            f"질문: {question}"
        )

        try:
            response = await client.chat.completions.create(
                model=self._settings.vlm.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                temperature=0.2,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception:
            logger.exception("VLM question call failed: %s", question)
            raise

        if not response.choices:
            return "응답 없음"
        return (response.choices[0].message.content or "").strip() or "응답 없음"

    def _build_context(self, location: str | None, timestamp: datetime | None) -> str:
        location_text = location or "미상"
        timestamp_text = timestamp.isoformat() if timestamp else "미상"
        return f"관측 위치: {location_text}\n관측 시각: {timestamp_text}"

    def _normalize_incident_type(self, answer: str) -> str:
        cleaned = " ".join(answer.split())
        return cleaned[:128] if cleaned else "unknown"

    def _infer_severity(self, q1: str, q2: str) -> str:
        text = f"{q1} {q2}".lower()
        if any(token in text for token in ["폭력", "범죄", "화재", "무기", "침입", "critical", "high"]):
            return "high"
        if any(token in text for token in ["위험", "충돌", "사고", "중간", "medium"]):
            return "medium"
        return "low"

    def _infer_confidence(self, q1: str, q2: str, q3: str, q4: str) -> float:
        answers = [q1, q2, q3, q4]
        non_empty = sum(1 for ans in answers if ans and ans.strip())
        base = 0.55 + (non_empty * 0.1)
        if any("불확실" in ans for ans in answers):
            base -= 0.15
        return max(0.1, min(0.99, round(base, 2)))

    def _compose_report(
        self,
        location: str | None,
        timestamp: datetime | None,
        q1: str,
        q2: str,
        q3: str,
        q4: str,
    ) -> str:
        parts = [
            f"위치: {location or '미상'}",
            f"시각: {timestamp.isoformat() if timestamp else '미상'}",
            f"위험성 판단: {q1}",
            f"사건 분류: {q2}",
            f"주요 인물/객체: {q3}",
            f"상황 요약: {q4}",
        ]
        return "\n".join(parts)

    def _build_incident_model(self, payload: dict[str, Any]) -> Any:
        try:
            return IncidentAnalysis.model_validate(payload)
        except ValidationError:
            logger.debug("IncidentAnalysis schema mismatch, filling required defaults")

        fields = IncidentAnalysis.model_fields
        prepared: dict[str, Any] = {}

        for field_name, field_info in fields.items():
            if field_name in payload and payload[field_name] is not None:
                prepared[field_name] = payload[field_name]
                continue

            annotation = field_info.annotation
            if annotation in (str, str | None):
                prepared[field_name] = ""
            elif annotation in (int, int | None):
                prepared[field_name] = 0
            elif annotation in (float, float | None):
                prepared[field_name] = 0.0
            elif annotation in (bool, bool | None):
                prepared[field_name] = False
            elif field_name.endswith("_at") or field_name == "timestamp":
                prepared[field_name] = datetime.utcnow()
            elif field_name.endswith("s"):
                prepared[field_name] = []
            else:
                prepared[field_name] = None

        return IncidentAnalysis.model_validate(prepared)
