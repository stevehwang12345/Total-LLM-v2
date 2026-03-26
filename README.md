# Total-LLM-v2 — AI 물리보안 관제 시스템

## 개요

Total-LLM-v2는 LLM과 VLM을 결합한 AI 기반 물리보안 통합 관제 시스템(PSIM)입니다. 채팅/RAG 기반 질의응답, 이미지/영상 자동 분석, 알람 라이프사이클 관리, 장비 헬스체크, 한글 PDF 보고서 생성, 문서 벡터 검색을 하나의 플랫폼에서 제공합니다. 백엔드는 FastAPI + asyncpg로 구성되며, vLLM 위에서 Qwen3.5-9B 모델을 구동합니다.

---

## 주요 기능

- 🤖 **AI 채팅 (LLM + RAG)** — LangGraph 기반 RAG 에이전트, Qdrant 벡터 검색, SSE 스트리밍 응답
- 📹 **이미지/영상 분석 (VLM)** — JPG/PNG/WebP/MP4 업로드, OpenCV 프레임 추출, 위험도 1~5단계 자동 판정, 위험도 3 이상 시 알람 자동 생성
- 🚨 **알람 관리** — 5단계 라이프사이클(신규 → 인지 → 처리중 → 해결 → 종료), Redis Pub/Sub SSE 실시간 스트림, 심각도/우선순위 필터
- 🖥️ **장비 관리** — 장비 등록/수정/삭제, 30초 주기 헬스체크 스케줄러, 5분 쿨다운, 헬스 이력 조회
- 📊 **보고서** — 한글 PDF 4종 자동 생성 (관제일지 / 사건보고서 / 장비점검일지 / 월간보고서), ReportLab 렌더링, 보고서 스케줄러
- 📁 **문서 관리** — PDF/DOCX/Markdown/TXT 업로드, 500자 청크 분할, Qdrant 벡터 임베딩, RAG 검색 연동

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | FastAPI 0.124+, asyncpg, Pydantic v2, LangGraph, LangChain |
| **AI / ML** | vLLM (Qwen/Qwen3.5-9B), Qwen3-Embedding-0.6B, OpenCV, ffmpeg |
| **Vector DB** | Qdrant v1.12, sentence-transformers, rank-bm25 |
| **Database** | PostgreSQL 15, Redis 7 |
| **Report** | ReportLab 4+, pypdf, python-docx |
| **Frontend** | React 19, TypeScript 5.9, Vite 7 |
| **UI** | shadcn/ui, Tailwind CSS v4, Radix UI, Recharts |
| **Routing** | TanStack Router v1, TanStack Query v5 |
| **Infra** | Docker Compose, nginx |

---

## 아키텍처

```
[Frontend :9004]
      |
    nginx
      |
[Backend :9002] ──── [vLLM :9000]       (Qwen3.5-9B, fp8 양자화)
      |          ──── [PostgreSQL :5434]  (관계형 데이터)
      |          ──── [Qdrant :6333]      (벡터 임베딩)
      |          ──── [Redis :6381]       (알람 Pub/Sub, 캐시)
```

---

## 빠른 시작

### 사전 요구사항

- Docker, Docker Compose
- NVIDIA GPU (vLLM 구동용, GPU 1번 사용)
- Hugging Face 토큰 (Qwen 모델 다운로드용)

### 환경 변수 설정

```bash
cp .env.example .env
# .env 파일에서 HUGGING_FACE_HUB_TOKEN 설정
```

### 실행

```bash
docker compose up -d --build
```

vLLM 컨테이너는 모델 로딩에 최대 3분이 소요됩니다. 헬스체크가 통과되면 백엔드가 자동으로 연결됩니다.

### 접속

| 서비스 | 주소 |
|--------|------|
| 프론트엔드 | http://localhost:9004 |
| 백엔드 API | http://localhost:9002 |
| API 문서 (Swagger) | http://localhost:9002/docs |
| Qdrant 대시보드 | http://localhost:6333/dashboard |

---

## API 엔드포인트

### 🤖 채팅 (`/api/chat`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/chat` | LLM/RAG 채팅 (SSE 스트리밍) |

### 📹 이미지/영상 분석 (`/api/analysis`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/analysis/upload` | 이미지/영상 업로드 및 VLM 분석 |
| `GET` | `/api/analysis` | 분석 목록 조회 |
| `GET` | `/api/analysis/{id}` | 분석 결과 상세 조회 |
| `GET` | `/api/analysis/{id}/media` | 원본 미디어 파일 반환 |

### 🚨 알람 관리 (`/api/alarms`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/alarms` | 알람 목록 (심각도/상태/우선순위 필터) |
| `GET` | `/api/alarms/stream` | 실시간 알람 SSE 스트림 |
| `GET` | `/api/alarms/stats` | 알람 통계 |
| `GET` | `/api/alarms/{id}` | 알람 상세 조회 |
| `POST` | `/api/alarms/{id}/acknowledge` | 알람 인지 처리 |
| `POST` | `/api/alarms/{id}/transition` | 알람 상태 전환 |

### 🖥️ 장비 관리 (`/api/devices`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/devices` | 장비 목록 (타입/상태 필터) |
| `GET` | `/api/devices/stats` | 장비 통계 (온라인/오프라인) |
| `POST` | `/api/devices` | 장비 등록 |
| `GET` | `/api/devices/{id}` | 장비 상세 조회 |
| `PUT` | `/api/devices/{id}` | 장비 정보 수정 |
| `DELETE` | `/api/devices/{id}` | 장비 삭제 |
| `GET` | `/api/devices/{id}/health` | 장비 헬스체크 |
| `GET` | `/api/devices/{id}/health/history` | 헬스 이력 조회 |

### 📊 보고서 (`/api/reports`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/reports/generate` | 보고서 생성 (`daily_log` / `incident` / `equipment` / `monthly`) |
| `GET` | `/api/reports` | 보고서 목록 |
| `GET` | `/api/reports/{id}/download` | PDF 다운로드 |
| `DELETE` | `/api/reports/{id}` | 보고서 삭제 |

### 📁 문서 관리 (`/api/documents`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/documents/upload` | 문서 업로드 및 벡터 임베딩 |
| `GET` | `/api/documents` | 문서 목록 |
| `DELETE` | `/api/documents/{id}` | 문서 및 벡터 삭제 |

### 시스템

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 서비스 상태 확인 |

---

## 표준 참조

| 표준 | 내용 |
|------|------|
| IEC 62676 | 영상감시 시스템 |
| ISO 27001 | 정보보안 관리 |
| ISO 22320 | 비상관리 및 대응 |
| 개인정보보호법 §25 | 영상정보처리기기 운영 |

---

## 프로젝트 구조

```
Total-LLM-v2/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/total_llm/
│   │   ├── api/              # 라우터 (chat, analysis, alarms, devices, documents, reports, system)
│   │   ├── core/             # 설정, 의존성, 예외 처리
│   │   ├── database/         # 커넥션 풀, 스키마 초기화
│   │   ├── models/           # Pydantic 스키마
│   │   └── services/         # 비즈니스 로직 (RAG, VLM, 알람, 장비, 보고서, 임베딩)
│   └── tests/                # pytest 테스트 스위트
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── components/       # 공통 UI 컴포넌트 (shadcn/ui 기반)
        ├── routes/           # TanStack Router 페이지 (chat, analysis, alarms, devices, documents, reports)
        └── features/         # 기능별 모듈
```

---

## 테스트

```bash
cd backend && python -m pytest tests/ -v
```

주요 테스트 항목:

- `test_alarm_lifecycle.py` — 알람 5단계 상태 전환
- `test_analysis_alarm_pipeline.py` — VLM 분석 후 알람 자동 생성 파이프라인
- `test_device_health.py` — 장비 헬스체크 및 스케줄러
- `test_report_pdf.py` — 한글 PDF 렌더링
- `test_smoke.py` — API 엔드포인트 스모크 테스트

---

## 라이선스

이 프로젝트는 내부 사용 목적으로 개발되었습니다.
