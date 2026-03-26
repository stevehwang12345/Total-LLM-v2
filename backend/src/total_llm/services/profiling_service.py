from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from total_llm.core.config import get_settings

logger = logging.getLogger(__name__)


class DeviceProfile(BaseModel):
    device_type: str = "Unknown"
    manufacturer: str = "Unknown"
    model_name: str = "Unknown"
    protocol: str = "Unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    suggested_device_id: str = ""


class ProfilingService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def profile_device(self, llm_client: Any, device_payload: dict[str, Any]) -> dict[str, Any]:
        profile_schema = {
            "name": "device_profile",
            "schema": {
                "type": "object",
                "properties": {
                    "device_type": {"type": "string"},
                    "manufacturer": {"type": "string"},
                    "model_name": {"type": "string"},
                    "protocol": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "suggested_device_id": {"type": "string"},
                },
                "required": [
                    "device_type",
                    "manufacturer",
                    "model_name",
                    "protocol",
                    "confidence",
                    "reasoning",
                    "suggested_device_id",
                ],
                "additionalProperties": False,
            },
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a network security device profiler. "
                    "Infer the most likely device profile from scan evidence. "
                    "Always return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Analyze this discovered device and infer profile fields. "
                    "Use conservative confidence when evidence is weak.\n"
                    f"{json.dumps(device_payload, ensure_ascii=False)}"
                ),
            },
        ]

        response = await llm_client.chat.completions.create(
            model=self._settings.llm.model_name,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_schema", "json_schema": profile_schema},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        raw_content = ""
        if response.choices:
            raw_content = response.choices[0].message.content or ""

        profile_obj = self._extract_json(raw_content)
        if profile_obj is None:
            logger.warning("Profiling JSON parse failed, returning fallback profile")
            return DeviceProfile(reasoning="Failed to parse LLM JSON output").model_dump()

        try:
            profile = DeviceProfile.model_validate(profile_obj)
            return profile.model_dump()
        except Exception:
            logger.exception("LLM profile schema validation failed")
            return DeviceProfile(reasoning="LLM profile schema validation failed").model_dump()

    async def re_verify_profile(
        self,
        llm_client: Any,
        device_payload: dict[str, Any],
        previous_profile: dict[str, Any],
        mismatches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        불일치가 발견된 프로파일에 대해 2차 LLM 검증을 수행한다.
        이전 프로파일과 구체적인 불일치 항목을 포함하여 LLM이 재분석하도록 한다.
        """
        profile_schema = {
            "name": "device_profile",
            "schema": {
                "type": "object",
                "properties": {
                    "device_type": {"type": "string"},
                    "manufacturer": {"type": "string"},
                    "model_name": {"type": "string"},
                    "protocol": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "suggested_device_id": {"type": "string"},
                },
                "required": [
                    "device_type",
                    "manufacturer",
                    "model_name",
                    "protocol",
                    "confidence",
                    "reasoning",
                    "suggested_device_id",
                ],
                "additionalProperties": False,
            },
        }

        mismatch_summary = "; ".join(
            f"{m.get('field')}: expected {m.get('expected')}, got {m.get('actual')} (evidence: {m.get('evidence')})"
            for m in mismatches
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are re-verifying a network security device profile. "
                    "A previous analysis had inconsistencies with scan evidence. "
                    "Re-analyze carefully and correct any mistakes. "
                    "Always return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Re-analyze this device profile. The previous analysis had inconsistencies.\n\n"
                    f"Scan evidence:\n{json.dumps(device_payload, ensure_ascii=False)}\n\n"
                    f"Previous profile:\n{json.dumps(previous_profile, ensure_ascii=False)}\n\n"
                    f"Inconsistencies found:\n{mismatch_summary}\n\n"
                    "Please re-analyze considering the scan evidence and the inconsistencies listed above. "
                    "Use conservative confidence when evidence is weak."
                ),
            },
        ]

        response = await llm_client.chat.completions.create(
            model=self._settings.llm.model_name,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_schema", "json_schema": profile_schema},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        raw_content = ""
        if response.choices:
            raw_content = response.choices[0].message.content or ""

        profile_obj = self._extract_json(raw_content)
        if profile_obj is None:
            logger.warning("Re-verification JSON parse failed, returning fallback profile")
            return DeviceProfile(reasoning="Failed to parse LLM JSON output").model_dump()

        try:
            profile = DeviceProfile.model_validate(profile_obj)
            return profile.model_dump()
        except Exception:
            logger.exception("LLM re-verification schema validation failed")
            return DeviceProfile(reasoning="LLM re-verification schema validation failed").model_dump()

    def _extract_json(self, raw_content: str) -> dict[str, Any] | None:
        if not raw_content:
            return None

        stripped = raw_content.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        candidate = stripped[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None
