"""
물리보안 VLM 분석 서비스 (v2)

UCF-Crime 표준 + 사용자 SOP 프롬프트 + 병렬 4-QA 하이브리드 파이프라인

Pipeline:
    1. 4개 QA 병렬 호출 (asyncio.gather)
       Q1: 장면 분석   Q2: 행동 분석
       Q3: 객체·인물   Q4: 환경·맥락
    2. 5번째 호출: 4-QA 결과 통합 → 6섹션 보고서 생성
    3. 16개 이벤트 카테고리 분류 + 5단계 위험도 + SOP 자동 매핑
"""

from __future__ import annotations

import asyncio
import base64
import cv2
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError as PydanticValidationError

from total_llm.core.config import get_settings
from total_llm.core.exceptions import VLMError, ValidationError
from total_llm.models import schemas as schema_models

logger = logging.getLogger(__name__)

IncidentAnalysis = getattr(schema_models, "IncidentAnalysis", schema_models.AnalysisResult)

# ============================================================
# 시스템 프롬프트 (모든 QA 호출에 공통)
# ============================================================
SYSTEM_PROMPT = """당신은 물리보안 관제 시스템(VMS)에서 15년 경력의 시니어 보안 분석가이자 컴퓨터 비전 전문가이다.
CCTV 영상 분석을 통해 보안 이벤트를 탐지하고, 실제 관제센터에서 즉시 사용할 수 있는 수준의 분석 보고서를 작성한다.

[분석 원칙]
- 객관적 사실 기반 작성 (추측 최소화, 근거 명시)
- 관제 보고서 스타일 유지 (간결 + 명확 + 정량적)
- 불필요한 감정 표현 금지
- 불확실한 경우 "확인 불가" 또는 "추가 확인 필요"로 명시"""

# ============================================================
# 4개 병렬 QA 프롬프트
# ============================================================
SECURITY_QA_PROMPTS: dict[str, str] = {
    "q1_scene": """[장면 분석 (Scene Understanding)]
이 CCTV 이미지의 장면을 분석하라.

보고 항목:
1. 환경 유형: 실내/실외, 구체적 장소 (주차장, 로비, 복도, 외곽 등)
2. 조명 조건: 주간/야간/저조도, 인공조명 유무
3. 카메라 화각: 광각/일반/줌, 사각지대 유무
4. 시야 내 주요 시설물: 출입문, 울타리, 차량, 계단 등
5. 전반적 상황 한 줄 요약

간결하고 사실적으로 작성하라.""",

    "q2_behavior": """[행동 분석 (Behavior Analysis)]
이 CCTV 이미지에서 감지되는 행동을 분석하라.

보고 항목:
1. 사람 수: 감지된 인원 수 (없으면 "인원 미감지"로 명시)
2. 행동 유형: 이동/정지/대화/뛰기/쓰러짐/물건 운반 등
3. 상호작용: 인원 간 접촉, 충돌, 추적 등의 상호작용 유무
4. 이상 행동 여부 판단:
   - 정상: 일반적 보행, 업무 활동
   - 의심: 배회(3분+), 장시간 정지, 반복 출입, 엿보기
   - 위험: 폭력, 침입, 도주, 물건 투기, 쓰러짐
5. 이상 행동 판단 근거 (구체적 행동 묘사)

이상 행동이 없으면 "이상 행동 미감지"로 명시하라.""",

    "q3_entities": """[객체·인물 분석 (Entity Identification)]
이 CCTV 이미지에서 식별 가능한 객체와 인물을 분석하라.

보고 항목:
1. 인물: 추정 연령대, 성별, 복장(상의/하의 색상·종류), 소지품
2. 차량: 차종, 색상, 번호판 식별 여부, 이동/정지 상태
3. 물체: 가방, 상자, 도구, 무기 의심 물체
4. 방치 물품: 주인 없는 물건 여부, 위치
5. 위치 관계: 객체 간 거리, 접근 방향

인물이 없는 경우 "인물 미감지 — 환경 중심 분석"으로 전환하라.""",

    "q4_context": """[환경·맥락 분석 (Contextual Assessment)]
이 CCTV 이미지의 보안 맥락을 종합 평가하라.

보고 항목:
1. 시간대 추정: 주간 업무시간/야간/심야/새벽 (조명·그림자 기반)
2. 구역 특성: 공개구역/제한구역/통제구역 추정
3. 보안 장비 가시성: CCTV, 울타리, 조명, 잠금장치 존재 여부
4. 취약 요소: 사각지대, 조명 부족, 울타리 손상, 개방된 출입구
5. 주변 상황 종합 평가 (정상/주의 필요/위험)

보안 관점에서 객관적으로 평가하라.""",
}

# ============================================================
# 통합 보고서 생성 프롬프트 (5번째 LLM 호출)
# ============================================================
SECURITY_REPORT_PROMPT = """당신은 물리보안 관제센터의 시니어 분석가이다.
아래 4개 분석 결과를 종합하여 표준 관제 보고서를 작성하라.

[촬영 정보]
- 위치: {location}
- 시각: {timestamp}
- 카메라: {camera_id}

[분석 결과]
Q1 장면 분석: {q1_scene}
Q2 행동 분석: {q2_behavior}
Q3 객체·인물: {q3_entities}
Q4 환경·맥락: {q4_context}

[출력 형식 — 반드시 아래 구조 그대로 작성할 것]

# 물리보안 분석 보고서

## 1. 장면 요약
- 한 줄 요약 (장소, 인원, 핵심 상황)

## 2. 객체 및 환경 분석
- 환경:
- 주요 객체:
- 카메라 평가:

## 3. 행동 분석
- 감지된 행동:
- 이상 행동 여부: 정상 / 의심 / 위험 (택일)
- 판단 근거:

## 4. 이벤트 정의
- 이벤트 유형: (아래 16개 중 하나만 선택)
  정상활동 | 배회 | 침입 | 폭력 | 싸움 | 넘어짐/낙상 |
  위협행위 | 도난/절도 | 기물파손 | 방화 | 폭발 | 추적/도주 |
  물품방치 | 무단주차 | 군중밀집 | 비정상행동
- 이벤트 설명:

## 5. 위험도 평가
- 위험 수준: 정보(1) / 낮음(2) / 중간(3) / 높음(4) / 매우높음(5) (택일)
- 판단 근거:
- 분석 신뢰도: (0.0 ~ 1.0)

## 6. 대응 방안
- 즉시 조치:
- 후속 조치:
- SOP 참조:

[작성 규칙]
- 객관적 사실 기반, 추측 시 "추정" 명시
- 간결하고 명확한 관제 보고서 스타일
- 이벤트 유형은 반드시 16개 중 하나 선택
- 위험 수준은 반드시 5단계 중 하나 선택"""

# ============================================================
# 이벤트 카테고리 (16개, UCF-Crime + 물리보안 확장)
# ============================================================
EVENT_CATEGORIES: dict[str, dict] = {
    "정상활동":    {"en": "Normal",            "risk": 1, "sop": None},
    "배회":       {"en": "Loitering",          "risk": 2, "sop": "SOP-L2"},
    "무단주차":    {"en": "Illegal_Parking",    "risk": 2, "sop": "SOP-L2"},
    "비정상행동":  {"en": "Abnormal_Behavior",  "risk": 3, "sop": "SOP-L3"},
    "도난/절도":   {"en": "Stealing",           "risk": 3, "sop": "SOP-L3"},
    "기물파손":    {"en": "Vandalism",          "risk": 3, "sop": "SOP-L3"},
    "물품방치":    {"en": "Abandoned_Object",   "risk": 3, "sop": "SOP-L3"},
    "군중밀집":    {"en": "Crowd_Gathering",    "risk": 3, "sop": "SOP-L3"},
    "위협행위":    {"en": "Threatening",        "risk": 4, "sop": "SOP-L4"},
    "싸움":       {"en": "Fighting",           "risk": 4, "sop": "SOP-L4"},
    "침입":       {"en": "Burglary",           "risk": 4, "sop": "SOP-L4"},
    "추적/도주":   {"en": "Fleeing",            "risk": 4, "sop": "SOP-L4"},
    "넘어짐/낙상": {"en": "Falling",            "risk": 4, "sop": "SOP-L4"},
    "폭력":       {"en": "Assault",            "risk": 5, "sop": "SOP-L5"},
    "방화":       {"en": "Arson",              "risk": 5, "sop": "SOP-L5"},
    "폭발":       {"en": "Explosion",          "risk": 5, "sop": "SOP-L5"},
}

# ============================================================
# 위험 수준별 SOP 대응 방안
# ============================================================
SOP_RESPONSE_MAP: dict[int, dict] = {
    1: {
        "label": "정보",
        "actions": ["상황 기록", "정상 모니터링 유지"],
        "escalation": None,
    },
    2: {
        "label": "낮음",
        "actions": ["CCTV 모니터링 강화", "해당 구역 주시", "상황 로그 기록"],
        "escalation": "보안 팀장 보고",
    },
    3: {
        "label": "중간",
        "actions": ["CCTV 집중 감시", "순찰 인력 해당 구역 배치", "보안 팀장 보고"],
        "escalation": "보안 책임자 보고",
    },
    4: {
        "label": "높음",
        "actions": [
            "경비 인력 현장 출동",
            "해당 구역 출입 통제",
            "CCTV 녹화 보존",
            "보안 책임자 보고",
        ],
        "escalation": "경찰(112) 신고 준비",
    },
    5: {
        "label": "매우높음",
        "actions": [
            "즉시 현장 출동",
            "112/119 신고",
            "전면 잠금(Lockdown)",
            "CCTV 증거 보존",
            "경영진 보고",
        ],
        "escalation": "비상대책본부 가동",
    },
}

# ============================================================
# 키워드 → 이벤트/위험 분류 (보고서 파싱 보조)
# ============================================================
INCIDENT_KEYWORD_MAP: dict[str, list[str]] = {
    "폭력":       ["폭력", "폭행", "구타", "때리", "주먹", "assault"],
    "싸움":       ["싸움", "몸싸움", "격투", "충돌", "fighting"],
    "침입":       ["침입", "무단 진입", "무단 출입", "불법 진입", "intrusion", "burglary"],
    "위협행위":   ["위협", "협박", "공격적 자세", "threatening"],
    "배회":       ["배회", "서성", "반복 출입", "loitering"],
    "넘어짐/낙상": ["넘어짐", "쓰러짐", "낙상", "lying", "fallen", "falling"],
    "도난/절도":   ["도난", "절도", "훔치", "stealing", "theft"],
    "기물파손":   ["파손", "부수", "vandalism"],
    "방화":       ["화재", "불", "방화", "arson"],
    "폭발":       ["폭발", "explosion"],
    "물품방치":   ["방치", "abandoned", "물품 방치"],
    "군중밀집":   ["군중", "밀집", "crowd"],
    "추적/도주":  ["도주", "추적", "도망", "fleeing"],
    "비정상행동": ["비정상", "이상 행동", "수상", "abnormal"],
}

RISK_KEYWORD_MAP: dict[int, list[str]] = {
    5: ["폭력", "방화", "폭발", "즉각", "긴급", "생명", "critical"],
    4: ["침입", "위협", "싸움", "높음", "high", "출동"],
    3: ["의심", "비정상", "중간", "medium", "주의"],
    2: ["배회", "낮음", "low", "경미"],
}


# ============================================================
# 메인 서비스 클래스
# ============================================================
class VLMService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def analyze_image(
        self,
        client: AsyncOpenAI,
        image_base64: str,
        location: str | None = None,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
    ) -> Any:
        if not image_base64 or not image_base64.strip():
            raise ValueError("image_base64 cannot be empty")

        ts = timestamp or datetime.utcnow()
        loc = location or "미상"
        cam = camera_id or "미상"

        # ── Phase 1: 4-QA 병렬 실행 ─────────────────────────
        q1, q2, q3, q4 = await asyncio.gather(
            self._ask_qa(client, image_base64, "q1_scene", loc, cam, ts),
            self._ask_qa(client, image_base64, "q2_behavior", loc, cam, ts),
            self._ask_qa(client, image_base64, "q3_entities", loc, cam, ts),
            self._ask_qa(client, image_base64, "q4_context", loc, cam, ts),
        )

        qa_results = {
            "q1_scene": q1,
            "q2_behavior": q2,
            "q3_entities": q3,
            "q4_context": q4,
        }

        # ── Phase 2: 통합 보고서 생성 ─────────────────────────
        report_md = await self._generate_report(client, loc, cam, ts, qa_results)

        # ── Phase 3: 보고서에서 구조화 데이터 추출 ────────────
        event_type = self._extract_event_type(report_md, q2)
        risk_level = self._extract_risk_level(report_md, event_type)
        confidence = self._estimate_confidence(q1, q2, q3, q4)
        actions = SOP_RESPONSE_MAP[risk_level]["actions"]
        sop_ref = EVENT_CATEGORIES.get(event_type, {}).get("sop")
        event_en = EVENT_CATEGORIES.get(event_type, {}).get("en", "Unknown")

        payload: dict[str, Any] = {
            "qa_results": qa_results,
            "incident_type": event_type,
            "incident_type_en": event_en,
            "severity": SOP_RESPONSE_MAP[risk_level]["label"],
            "risk_level": risk_level,
            "confidence": confidence,
            "report": report_md,
            "recommended_actions": actions,
            "sop_reference": sop_ref,
            "location": loc,
            "timestamp": ts,
            # 하위 호환 필드
            "summary": report_md[:200] + "..." if len(report_md) > 200 else report_md,
            "description": q4,
        }

        return self._build_model(payload)

    async def analyze_video(
        self,
        client: AsyncOpenAI,
        video_path: str | Path,
        location: str | None = None,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
    ) -> Any:
        path = Path(video_path)
        if not path.exists():
            raise ValueError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise VLMError(f"프레임 추출 실패: 영상 파일을 열 수 없습니다 ({path.name})")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                raise VLMError("프레임 추출 실패: 프레임 정보를 읽을 수 없습니다")

            duration_sec = total_frames / fps
            if duration_sec > 60:
                raise ValidationError("영상 길이가 60초를 초과합니다")

            keyframe_indices = sorted(
                {
                    0,
                    total_frames // 3,
                    (total_frames * 2) // 3,
                    max(total_frames - 1, 0),
                }
            )
            keyframes: list[Any] = []
            for frame_idx in keyframe_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret_kf, frame_kf = cap.read()
                if ret_kf and frame_kf is not None:
                    keyframes.append(frame_kf)

            if not keyframes:
                raise VLMError("프레임 추출 실패: 키프레임을 추출할 수 없습니다")

            mid_frame_idx = total_frames // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                raise VLMError("프레임 추출 실패: 대표 프레임을 읽을 수 없습니다")

            success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                raise VLMError("프레임 추출 실패: JPEG 인코딩 오류")
            image_base64 = base64.b64encode(buf.tobytes()).decode("utf-8")
        finally:
            cap.release()

        loc = location or "미상"
        video_context = f"{loc} [영상: {duration_sec:.1f}초, 대표프레임: {mid_frame_idx}/{total_frames}]"

        result = await self.analyze_image(
            client=client,
            image_base64=image_base64,
            location=video_context,
            timestamp=timestamp,
            camera_id=camera_id,
        )

        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        payload["media_type"] = "video"
        return self._build_model(payload)

    # ── QA 단일 호출 ──────────────────────────────────────────
    async def _ask_qa(
        self,
        client: AsyncOpenAI,
        image_b64: str,
        qa_key: str,
        location: str,
        camera_id: str,
        timestamp: datetime,
    ) -> str:
        context = (
            f"[관측 정보]\n"
            f"- 위치: {location}\n"
            f"- 카메라: {camera_id}\n"
            f"- 시각: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        question = SECURITY_QA_PROMPTS[qa_key]
        prompt = context + question

        try:
            resp = await client.chat.completions.create(
                model=self._settings.vlm.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    },
                ],
                temperature=0.2,
                max_tokens=512,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception:
            logger.exception("VLM QA call failed: %s", qa_key)
            raise

        return (resp.choices[0].message.content or "응답 없음").strip() if resp.choices else "응답 없음"

    # ── 5번째 통합 보고서 호출 ────────────────────────────────
    async def _generate_report(
        self,
        client: AsyncOpenAI,
        location: str,
        camera_id: str,
        timestamp: datetime,
        qa: dict[str, str],
    ) -> str:
        prompt = SECURITY_REPORT_PROMPT.format(
            location=location,
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            camera_id=camera_id,
            q1_scene=qa["q1_scene"],
            q2_behavior=qa["q2_behavior"],
            q3_entities=qa["q3_entities"],
            q4_context=qa["q4_context"],
        )
        try:
            resp = await client.chat.completions.create(
                model=self._settings.vlm.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception:
            logger.exception("Report generation failed")
            raise

        return (resp.choices[0].message.content or "").strip() if resp.choices else ""

    # ── 이벤트 유형 추출 ─────────────────────────────────────
    def _extract_event_type(self, report: str, q2: str) -> str:
        text = f"{report}\n{q2}".lower()

        # 1. 보고서의 "이벤트 유형:" 라인에서 직접 추출
        for line in report.splitlines():
            if "이벤트 유형" in line:
                for category in EVENT_CATEGORIES:
                    if category in line:
                        return category

        # 2. 키워드 매칭
        for category, keywords in INCIDENT_KEYWORD_MAP.items():
            if any(kw in text for kw in keywords):
                return category

        return "정상활동"

    # ── 위험 수준 추출 ───────────────────────────────────────
    def _extract_risk_level(self, report: str, event_type: str) -> int:
        # 1. 보고서의 "위험 수준:" 라인에서 직접 추출
        for line in report.splitlines():
            if "위험 수준" in line:
                if "매우높음" in line or "(5)" in line:
                    return 5
                if "높음" in line or "(4)" in line:
                    return 4
                if "중간" in line or "(3)" in line:
                    return 3
                if "낮음" in line or "(2)" in line:
                    return 2
                if "정보" in line or "(1)" in line:
                    return 1

        # 2. 이벤트 카테고리 기본값 사용
        default = EVENT_CATEGORIES.get(event_type, {}).get("risk", 1)
        return default

    # ── 신뢰도 추정 ─────────────────────────────────────────
    def _estimate_confidence(self, q1: str, q2: str, q3: str, q4: str) -> float:
        answers = [q1, q2, q3, q4]
        non_empty = sum(1 for a in answers if a and a not in ("응답 없음", ""))
        base = 0.50 + non_empty * 0.10

        uncertain_words = ["불확실", "확인 불가", "확인 필요", "추정", "판단 어려움", "알 수 없"]
        penalty = sum(0.05 for a in answers if any(w in a for w in uncertain_words))

        empty_scene_words = ["분석 불가", "이미지 없음", "사람 없음", "인물 미감지"]
        if any(any(w in a for w in empty_scene_words) for a in answers):
            base -= 0.20

        return round(max(0.10, min(0.98, base - penalty)), 2)

    # ── Pydantic 모델 빌드 ──────────────────────────────────
    def _build_model(self, payload: dict[str, Any]) -> Any:
        try:
            return IncidentAnalysis.model_validate(payload)
        except PydanticValidationError:
            logger.debug("IncidentAnalysis schema mismatch, using fallback")

        fields = IncidentAnalysis.model_fields
        prepared: dict[str, Any] = {}
        for name, info in fields.items():
            if name in payload and payload[name] is not None:
                prepared[name] = payload[name]
                continue
            ann = info.annotation
            if ann in (str, str | None):
                prepared[name] = ""
            elif ann in (int, int | None):
                prepared[name] = 0
            elif ann in (float, float | None):
                prepared[name] = 0.0
            elif ann in (bool, bool | None):
                prepared[name] = False
            elif name.endswith("_at") or name == "timestamp":
                prepared[name] = datetime.utcnow()
            elif name.endswith("s"):
                prepared[name] = []
            else:
                prepared[name] = None

        return IncidentAnalysis.model_validate(prepared)
