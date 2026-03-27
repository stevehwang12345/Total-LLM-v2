# Total-LLM v2 — AI 물리보안 관제 시스템

> 네트워크 장비 자동 탐지 · LLM 프로파일링 · 정합성 검증 · AI 채팅 운영 지원

---

## 목차

1. [개요](#개요)
2. [주요 기능](#주요-기능)
3. [기술 스택](#기술-스택)
4. [아키텍처](#아키텍처)
5. [시스템 요구 사항](#시스템-요구-사항)
6. [설치 가이드](#설치-가이드)
7. [환경 변수 레퍼런스](#환경-변수-레퍼런스)
8. [디스커버리 파이프라인](#디스커버리-파이프라인)
9. [프로파일 정합성 검증](#프로파일-정합성-검증)
10. [LLM 채팅 & Function Calling](#llm-채팅--function-calling)
11. [API 레퍼런스](#api-레퍼런스)
12. [프론트엔드 화면 구성](#프론트엔드-화면-구성)
13. [데이터베이스 스키마](#데이터베이스-스키마)
14. [프로젝트 구조](#프로젝트-구조)
15. [개발 환경 설정](#개발-환경-설정)
16. [테스트](#테스트)
17. [운영 가이드](#운영-가이드)
18. [트러블슈팅](#트러블슈팅)
19. [표준 참조](#표준-참조)

---

## 개요

Total-LLM v2는 **CCTV · 출입통제장치(ACU) 등 물리 보안 장비**를 LLM으로 자동 탐지·분류·운영하는 플랫폼입니다. 운영자가 수동으로 장비를 등록하던 기존 방식을 벗어나, **네트워크 스캔 → LLM 프로파일링 → 정합성 검증 → 자동/수동 등록** 흐름으로 온보딩을 자동화합니다.

등록 이후에는 **AI 채팅 인터페이스**를 통해 자연어로 장비 현황 조회, 건강 상태 확인, 스캔 이력 조회 등을 수행할 수 있습니다.

| 항목 | 기존 방식 | Total-LLM v2 |
|------|-----------|--------------|
| 장비 등록 | 수동 입력 | 네트워크 스캔 → LLM 자동 분류 → 1-click 등록 |
| 장비 식별 | IP/MAC 수동 입력 | ONVIF · mDNS · 포트 · 벤더 OUI 자동 수집 |
| 불확실한 분류 | 운영자 직접 판단 | 규칙 기반 정합성 검증 + LLM 재검증 + 수동 확인 폼 |
| 운영 쿼리 | 대시보드 클릭 | 자연어 채팅 + Function Calling |

---

## 주요 기능

### 네트워크 장비 디스커버리
- CIDR 범위 입력 → 내부망 ARP 스캔 (Scapy)
- 포트 스캔 (nmap): 80, 443, 502, 554, 8080, 8443, 8554, 37777 등 12개 포트
- ONVIF 카메라 탐지 (WS-Discovery) · mDNS/Bonjour 서비스 탐지 (Zeroconf)
- HTTP 배너 수집 · MAC OUI 벤더 매핑 · Reverse DNS hostname 조회

### LLM 프로파일링 + 정합성 검증
- 수집된 스캔 증거를 Qwen3.5-9B에 전달해 장비 타입·제조사·프로토콜 추론
- **7개 규칙 기반** 정합성 엔진이 LLM 결과를 스캔 증거와 교차 검증
- 불일치 시 2차 LLM 재검증 자동 실행 (최대 1회)
- 재검증 후에도 불일치면 **수동 입력 폼** 표시 (LLM 추천값 pre-fill + 경고 하이라이트)

### AI 채팅 with Function Calling
- 도구 모드 활성화 시 LLM이 `list_devices` · `get_device_health` · `get_device_health_history` · `list_scan_sessions` 4가지 도구를 직접 호출
- SSE로 `tool_call` → `tool_result` → `content` 실시간 스트리밍

### 이미지/영상 분석 (VLM)
- JPG/PNG/WebP/MP4 업로드, OpenCV 프레임 추출, 위험도 1~5단계 자동 판정

### 알람 관리
- 5단계 라이프사이클 · Redis Pub/Sub SSE 실시간 스트림

### 장비 관리
- 장비 CRUD + 30초 주기 헬스체크 + ping 미설치 시 TCP 포트 fallback

### 문서 RAG 검색
- PDF·DOCX·Markdown 업로드 → Qdrant 벡터 + BM25 하이브리드 검색

### 보고서 자동 생성
- 한글 PDF 4종: 관제일지 / 사건보고서 / 장비점검일지 / 월간보고서

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | FastAPI 0.135, asyncpg, Pydantic v2, LangGraph, LangChain |
| **AI / ML** | vLLM (Qwen/Qwen3.5-9B fp8), Qwen3-Embedding-0.6B, OpenCV |
| **Vector DB** | Qdrant v1.12, sentence-transformers, rank-bm25 |
| **Database** | PostgreSQL 15, Redis 7 |
| **Frontend** | React 19, TypeScript 5.9, Vite 7, shadcn/ui, TanStack Router |
| **Scanner** | Scapy, python-nmap, Zeroconf, WS-Discovery |
| **Infra** | Docker Compose, nginx |

---

## 아키텍처

```
┌────────────────────────────────────────────────────────────┐
│                   사용자 브라우저  :9004                      │
│          React + Vite + TanStack Router + shadcn/ui         │
└────────────────────────────┬───────────────────────────────┘
                             │ nginx reverse proxy
                             ▼
┌────────────────────────────────────────────────────────────┐
│                 FastAPI Backend  :9002                       │
│                                                              │
│  /devices  /discovery  /chat  /alarms  /analysis  /reports  │
│                                                              │
│  DeviceService  DiscoveryService  ToolAgent  AlarmService   │
│  HealthScheduler ProfilingService DeviceTools ReportService │
│                 ConsistencyValidator (7 rules)               │
└──┬──────────────────┬─────────────────────────────────┬─────┘
   │                  │                                 │
   │    ┌─────────────┴──────────────────┐              │
   │    │     Scanner Sidecar  :9003      │              │
   │    │  ARP · nmap · ONVIF · mDNS      │              │
   │    │  HTTP Banner · Reverse DNS       │              │
   │    └────────────────────────────────┘              │
   │                                                     │
┌──▼──────┐  ┌────────┐  ┌──────┐  ┌────────────────────▼┐
│PostgreSQL│  │ Qdrant │  │Redis │  │  vLLM  :9000        │
│  :5434   │  │ :6333  │  │:6381 │  │  Qwen3.5-9B (fp8)  │
└──────────┘  └────────┘  └──────┘  └─────────────────────┘
```

---

## 시스템 요구 사항

### 최소 사양

| 항목 | 요구 사항 |
|------|-----------|
| **OS** | Ubuntu 22.04+ / RHEL 8+ / Rocky Linux 9+ (x86_64) |
| **CPU** | 8코어 이상 |
| **RAM** | 32GB 이상 |
| **GPU** | NVIDIA GPU **16GB+ VRAM** (RTX A4000, RTX 4080 등) |
| **디스크** | 100GB 이상 여유 (모델 캐시 ~18GB + DB 데이터) |
| **Docker** | Docker Engine 24.0+ |
| **Docker Compose** | v2.20+ |
| **NVIDIA Driver** | 535+ |
| **CUDA** | 12.1+ |

> **참고**: Qwen3.5-9B (fp8 양자화) 모델은 약 10~12GB VRAM을 사용하므로 16GB GPU에서 동작 가능합니다.

### 권장 사양

| 항목 | 권장 |
|------|------|
| **GPU** | NVIDIA RTX 4000 Ada 20GB 또는 RTX 4090 24GB |
| **RAM** | 64GB |
| **디스크** | NVMe SSD 500GB+ |
| **네트워크** | 스캔 대상과 동일 L2 세그먼트 (ARP 스캔용) |

> **실제 검증 환경**: RTX 4000 Ada 20GB × 2, RAM 252GB, 32코어, NVMe 870GB

---

## 설치 가이드

### 1단계: NVIDIA GPU 드라이버 설치

```bash
# 현재 드라이버 확인
nvidia-smi

# 드라이버가 없는 경우 (Ubuntu 22.04)
sudo apt update
sudo apt install -y nvidia-driver-535
sudo reboot

# 재부팅 후 확인 — Driver Version >= 535, CUDA >= 12.1
nvidia-smi
```

### 2단계: Docker Engine 설치

```bash
# 기존 Docker 제거
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Docker 공식 저장소 추가
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker 설치
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker

# 확인
docker --version           # 24.0+
docker compose version     # v2.20+
```

### 3단계: NVIDIA Container Toolkit 설치

```bash
# 저장소 추가
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

# Docker 런타임 설정
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# GPU 접근 확인
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 4단계: 프로젝트 클론 및 환경 설정

```bash
# 저장소 클론
git clone https://github.com/stevehwang12345/Total-LLM-v2.git
cd Total-LLM-v2

# 환경 변수 파일 생성
cp .env.example .env
```

`.env` 파일 편집:

```bash
nano .env
```

**필수 변경**:

```env
# HuggingFace 토큰 (모델 다운로드에 필요한 경우)
HUGGING_FACE_HUB_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxx

# 운영 환경 — 반드시 변경
JWT_SECRET=your-strong-random-secret-key-here
```

**GPU 번호 변경** (기본 GPU 1번 → 0번으로 변경 시):

```bash
nano docker-compose.yml
```

vllm 서비스의 `NVIDIA_VISIBLE_DEVICES`와 `device_ids`를 `"0"`으로 변경

### 5단계: 전체 서비스 기동

```bash
# 빌드 및 기동
docker compose up -d --build

# 기동 상태 확인
docker compose ps

# 전체 로그 (Ctrl+C로 종료)
docker compose logs -f
```

> **주의**: vLLM은 최초 실행 시 모델 다운로드(~18GB) + 로딩에 약 **5~10분** 소요됩니다.
> 이후 실행부터는 캐시된 모델 사용으로 약 2~3분이면 준비됩니다.

### 6단계: 기동 확인

```bash
# 전체 서비스 상태 — 모두 healthy/Up 상태여야 함
docker compose ps

# 백엔드 헬스체크
curl http://localhost:9002/health

# vLLM 모델 확인
curl http://localhost:9000/v1/models

# 스캐너 확인
curl http://localhost:9003/health

# 프론트엔드 — 브라우저에서 접속
# http://localhost:9004
```

| 서비스 | 포트 | 확인 URL |
|--------|------|----------|
| 프론트엔드 | 9004 | http://localhost:9004 |
| 백엔드 API | 9002 | http://localhost:9002/health |
| Swagger UI | 9002 | http://localhost:9002/docs |
| vLLM | 9000 | http://localhost:9000/v1/models |
| 스캐너 | 9003 | http://localhost:9003/health |
| PostgreSQL | 5434 | `psql -h localhost -p 5434 -U total_llm` |
| Qdrant | 6333 | http://localhost:6333/dashboard |
| Redis | 6381 | `redis-cli -p 6381 ping` |

### 7단계: 첫 번째 디스커버리 실행

1. `http://localhost:9004` 접속
2. 사이드바 → **디스커버리**
3. CIDR 입력 (예: `192.168.1.0/24`) → **스캔 시작**
4. 완료 후 **프로파일** → 정합성 검증 확인 → **등록**

---

## 환경 변수 레퍼런스

전체 변수는 `.env.example`에 한글 주석으로 설명되어 있습니다.

### LLM / AI

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HUGGING_FACE_HUB_TOKEN` | (없음) | HuggingFace 모델 다운로드 토큰 |
| `VLLM_BASE_URL` | `http://vllm:9000/v1` | vLLM 엔드포인트 |
| `LLM_MODEL_NAME` | `Qwen/Qwen3.5-9B` | 텍스트 생성 모델 |
| `EMBEDDING_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | 임베딩 모델 |

### 데이터베이스

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `POSTGRES_PASSWORD` | `total_llm_dev` | **운영 환경 변경 필수** |
| `SCANNER_BASE_URL` | `http://scanner:9003` | 스캐너 URL |

### 보안

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `JWT_SECRET` | `change-me-in-production` | **운영 환경 변경 필수** |
| `CORS_ORIGINS` | `["http://localhost:9004"]` | CORS 허용 Origin |

---

## 디스커버리 파이프라인

### 스캐너 동작 순서

```
1. ARP 스캔 (Scapy)        → IP/MAC 목록
2. 포트 스캔 (nmap)        → 12개 보안 포트
3. MAC OUI 벤더 매핑       → 제조사 식별
4. ONVIF WS-Discovery      → 카메라 탐지
5. mDNS/Bonjour            → 서비스 탐지
6. HTTP 배너 수집           → 서버명, WWW-Auth
7. Reverse DNS             → hostname
```

---

## 프로파일 정합성 검증

### 7개 규칙

| # | 조건 | 기대값 | 심각도 |
|---|------|--------|--------|
| R1 | ONVIF 정보 있음 | CCTV | high |
| R2 | mDNS `_rtsp._tcp` | CCTV | medium |
| R3 | 포트 554/8554 열림 | CCTV + RTSP | high |
| R4 | 포트 502 열림 | ACU + Modbus | high |
| R5 | HTTP Digest auth | CCTV 가능성 | low |
| R6 | 카메라 벤더 MAC | CCTV | medium |
| R7 | confidence < 0.5 | 자동 불일치 | high |

**점수**: `score = 1.0 - weighted/5.0`, **통과 조건**: `score >= 0.6 AND high_count == 0`

**검증 실패 시**: 수동 입력 폼 (LLM 추천값 pre-fill, 불일치 필드 경고 표시)

---

## LLM 채팅 & Function Calling

### 4가지 도구

| 도구 | 설명 |
|------|------|
| `list_devices` | 장비 목록 조회 (타입/상태 필터) |
| `get_device_health` | 장비 실시간 헬스체크 |
| `get_device_health_history` | 헬스체크 이력 |
| `list_scan_sessions` | 디스커버리 스캔 목록 |

### SSE 이벤트

```
← {"type":"tool_call","tool_name":"list_devices","arguments":{...}}
← {"type":"tool_result","tool_name":"list_devices","result":{...}}
← {"type":"content","content":"현재 오프라인 장비는..."}
← {"type":"done"}
```

---

## API 레퍼런스

전체 API 문서: `http://localhost:9002/docs`

### 디스커버리 (`/api/discovery`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/scans` | 스캔 시작 |
| `GET` | `/scans` | 스캔 목록 |
| `GET` | `/scans/{id}` | 스캔 상태 |
| `GET` | `/scans/{id}/results` | 발견 장비 |
| `POST` | `/scans/{id}/devices/{did}/profile` | LLM 프로파일링 + 정합성 검증 |
| `POST` | `/scans/{id}/devices/{did}/register` | 장비 등록 (manual_override 지원) |

### 채팅 (`/api/chat`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/completions` | LLM 채팅 SSE (use_tools 지원) |

### 장비 (`/api/devices`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/` | 목록 |
| `GET` | `/stats` | 통계 |
| `POST` | `/` | 등록 |
| `GET/PUT/DELETE` | `/{id}` | 상세/수정/삭제 |
| `GET` | `/{id}/health` | 헬스체크 |
| `GET` | `/{id}/health/history` | 이력 |

### 알람 (`/api/alarms`) · 분석 (`/api/analysis`) · 보고서 (`/api/reports`) · 문서 (`/api/documents`)

Swagger UI (`/docs`)에서 상세 확인 가능

---

## 프론트엔드 화면 구성

| 메뉴 | 경로 | 주요 기능 |
|------|------|-----------|
| 대시보드 | `/` | 장비 현황 요약 |
| 장비 관리 | `/devices` | CRUD + 헬스체크 + 등록 방식 뱃지 |
| 디스커버리 | `/discovery` | 스캔 + 프로파일 + 정합성 뱃지 + 수동 입력 폼 |
| 채팅 | `/chat` | AI 채팅 + 도구 모드 |
| 알람 | `/alarms` | 알람 관리 |
| 영상 분석 | `/analysis` | VLM 분석 |
| 문서 | `/documents` | RAG 문서 |
| 보고서 | `/reports` | PDF 생성 |

---

## 데이터베이스 스키마

| 테이블 | 용도 |
|--------|------|
| `devices` | 등록된 장비 |
| `scan_sessions` | 디스커버리 스캔 세션 |
| `discovered_devices` | 발견 장비 (staging, llm_profile + consistency_result 포함) |
| `alarms` | 알람 라이프사이클 |
| `device_health_logs` | 헬스체크 이력 |
| `conversations` / `messages` | 채팅 이력 |
| `documents_meta` | 문서 메타 |
| `reports` / `analyses` | 보고서, 분석 결과 |

---

## 프로젝트 구조

```
Total-LLM-v2/
├── docker-compose.yml          # 7개 서비스 오케스트레이션
├── .env.example                # 환경 변수 (한글 주석)
├── backend/
│   ├── Dockerfile              # Python 3.11 + ffmpeg + 나눔폰트
│   ├── pyproject.toml          # 40+ 의존성
│   ├── src/total_llm/
│   │   ├── app.py              # FastAPI 앱
│   │   ├── core/               # config, DI, 예외, JWT
│   │   ├── models/             # Pydantic 스키마
│   │   ├── database/           # DDL + DB 초기화
│   │   ├── api/                # 8개 라우터
│   │   └── services/           # 12개 서비스
│   └── tests/                  # 79 테스트 (pytest)
├── frontend/
│   ├── Dockerfile              # Node 20 빌드 → nginx
│   ├── nginx.conf              # API 프록시 + SSE + SPA
│   └── src/routes/             # 8개 페이지
├── scanner/
│   ├── Dockerfile              # Python 3.11 + nmap
│   ├── requirements.txt
│   └── main.py                 # FastAPI 스캐너
└── data/                       # 런타임 데이터 (gitignore)
```

---

## 개발 환경 설정

### 백엔드

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export POSTGRES_HOST=localhost POSTGRES_PORT=5434
export VLLM_BASE_URL=http://localhost:9000/v1
uvicorn total_llm.app:app --reload --port 9002
```

### 프론트엔드

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # 프로덕션 빌드
```

### 스캐너

```bash
cd scanner
pip install -r requirements.txt
sudo uvicorn main:app --reload --port 9003   # NET_RAW 필요
```

---

## 테스트

```bash
cd backend
pytest tests/ -v    # 79 passed, 2 skipped
```

| 파일 | 케이스 | 범위 |
|------|--------|------|
| test_consistency.py | 15 | 정합성 7규칙 |
| test_discovery_api.py | 11 | 디스커버리 API |
| test_profiling_service.py | 5 | LLM 프로파일링 |
| test_tool_agent.py | 3 | Function Calling |
| test_device_health.py | 8 | 헬스체크 |
| test_alarm_lifecycle.py | 6 | 알람 상태 전이 |
| 기타 | 31 | 보고서, 스모크 등 |

---

## 운영 가이드

### 서비스 관리

```bash
docker compose up -d            # 기동
docker compose down             # 종료 (데이터 보존)
docker compose up -d --build backend   # 특정 서비스 재빌드
docker compose logs -f backend  # 실시간 로그
```

### DB 완전 초기화

```bash
docker compose stop postgres
docker run --rm -v "$(pwd)/data/postgres_data:/target" alpine sh -c "rm -rf /target/*"
docker compose up -d postgres && docker compose up -d --build backend
```

---

## 트러블슈팅

### vLLM 시작 실패

```bash
nvidia-smi                          # GPU 메모리 확인
docker compose logs vllm --tail=50  # 에러 로그
```
- VRAM 부족 → `--gpu-memory-utilization` 값 낮추기
- 모델 다운로드 실패 → `HUGGING_FACE_HUB_TOKEN` 확인
- GPU 번호 불일치 → `docker-compose.yml`의 device_ids 확인

### 디스커버리 장비 미발견

```bash
docker compose logs scanner --tail=30
docker compose exec backend curl http://scanner:9003/health
```
- L2 세그먼트 불일치 (ARP 스캔 제한)
- 타임아웃 부족 → `timeout_sec` 증가

### LLM 프로파일링 실패

```bash
curl http://localhost:9000/v1/models   # vLLM 상태 확인
docker compose logs backend | grep -i "profile\|llm"
```

### 프론트엔드 API 연결 실패

- `CORS_ORIGINS`에 프론트엔드 URL 포함 확인
- `frontend/nginx.conf` 프록시 설정 확인

---

## 표준 참조

| 표준 | 내용 |
|------|------|
| IEC 62676 | 영상감시 시스템 |
| ISO 27001 | 정보보안 관리 |
| ISO 22320 | 비상관리 및 대응 |
| 개인정보보호법 §25 | 영상정보처리기기 운영 |

---

## LLM 동작 방식 및 프롬프트 상세

Total-LLM v2는 기능별로 **Qwen3.5-9B 모델**을 다르게 활용합니다.

---

### 1. RAG 채팅 에이전트 (LangGraph Agentic RAG)

**파일**: `backend/src/total_llm/services/rag_agent.py`

질문 하나당 **최대 5번의 LLM 호출**로 구성된 자기수정(self-correction) 파이프라인입니다.

#### 그래프 구조

```
시작 → [쿼리 분류] → [문서 검색] → [문서 관련도 평가] → [생성 여부 결정]
                                                              ↙         ↘
                                                     [쿼리 재작성]   [응답 생성]
                                                            ↓              ↓
                                                        [재검색]   [응답 품질 평가]
                                                                         ↙      ↘
                                                                    [출력]  [쿼리 재작성]
```

#### 호출 1 — 쿼리 복잡도 분류

```
[System]
You classify user queries for retrieval complexity.
Return strict JSON with key route only.

[User]
Choose one route: simple, hybrid, complex.
simple: straightforward factual question
hybrid: requires moderate context synthesis
complex: multi-step reasoning, broad context, or analytical task

Query: {user_query}
Return JSON: {"route":"simple|hybrid|complex"}
```

검색량 결정: `simple` → 4개, `hybrid` → 8개, `complex` → 12개

#### 호출 2 — 문서 관련도 평가 (검색된 문서 수만큼 반복)

```
[System]
You score relevance between query and candidate document chunk.
Return strict JSON only.

[User]
Query: {query}
Document: {document_text}
Return JSON: {"score":0..1,"relevant":true|false,"reason":"..."}
```

임계값: `score ≥ 0.55` → 관련 문서로 분류

#### 호출 3 — 쿼리 재작성 (관련 문서 부족 시, 최대 2회)

```
[System]
You rewrite search queries to improve retrieval quality while preserving intent.
Return strict JSON only.

[User]
Original query: {query}
Reason: {insufficient_retrieval | generation_quality}
Current snippets: {현재 검색된 문서 요약}
Return JSON: {"rewritten_query":"..."}
```

#### 호출 4 — 응답 생성 (스트리밍)

```
[System]
You are a careful RAG assistant. Provide grounded answers only.

[User]
Answer the user question using only the retrieved context.
If information is insufficient, state exactly what is missing.
Cite source tags like [source:...].

Question: {query}

Retrieved context:
[source:파일명]
{문서 청크 내용}
...
```

Temperature: `0.2` / SSE 토큰 단위 실시간 스트리밍

#### 호출 5 — 응답 품질 평가

```
[System]
You are a strict evaluator for grounded RAG answers.
Return strict JSON only.

[User]
User query: {query}
Retrieved evidence: {관련 문서}
Assistant answer: {생성된 응답}
Evaluate groundedness and usefulness.
Return JSON: {"grounded":true|false,"helpful":true|false,"score":0..1,"reason":"..."}
```

`score ≥ 0.6` 통과 시 출력, 미달 시 쿼리 재작성 후 재시도 (최대 2회)

---

### 2. VLM 영상·이미지 분석 (4-QA 병렬 파이프라인)

**파일**: `backend/src/total_llm/services/vlm_service.py`

이미지/영상 1개당 **5번의 LLM 호출** (4개 병렬 + 1개 통합).

#### 공통 시스템 프롬프트 (모든 QA 호출 공유)

```
당신은 물리보안 관제 시스템(VMS)에서 15년 경력의 시니어 보안 분석가이자 컴퓨터 비전 전문가이다.
CCTV 영상 분석을 통해 보안 이벤트를 탐지하고, 실제 관제센터에서 즉시 사용할 수 있는 수준의 분석 보고서를 작성한다.

[분석 원칙]
- 객관적 사실 기반 작성 (추측 최소화, 근거 명시)
- 관제 보고서 스타일 유지 (간결 + 명확 + 정량적)
- 불필요한 감정 표현 금지
- 불확실한 경우 "확인 불가" 또는 "추가 확인 필요"로 명시
```

#### Phase 1: 4개 QA 병렬 호출 (`asyncio.gather`)

| QA | 분석 영역 | 주요 항목 |
|----|-----------|-----------|
| Q1 | 장면 분석 | 환경 유형, 조명, 카메라 화각, 시설물 |
| Q2 | 행동 분석 | 인원 수, 행동 유형, 이상 행동 여부 |
| Q3 | 객체·인물 | 인물 복장, 차량, 방치 물품, 위치 관계 |
| Q4 | 환경·맥락 | 시간대, 구역 특성, 보안 장비, 취약 요소 |

#### Phase 2: 통합 보고서 생성 (5번째 호출)

4개 QA 결과를 받아 **6섹션 표준 관제 보고서** 생성:

```
1. 장면 요약
2. 객체 및 환경 분석
3. 행동 분석
4. 이벤트 정의 (16개 카테고리 중 선택)
5. 위험도 평가 (1~5단계)
6. 대응 방안 (즉시 조치 + 후속 조치 + SOP 참조)
```

#### 이벤트 카테고리 (16개, UCF-Crime 기반 + 물리보안 확장)

| 위험도 | 카테고리 | SOP |
|--------|---------|-----|
| 1 (정보) | 정상활동 | — |
| 2 (낮음) | 배회, 무단주차 | SOP-L2 |
| 3 (중간) | 비정상행동, 도난/절도, 기물파손, 물품방치, 군중밀집 | SOP-L3 |
| 4 (높음) | 위협행위, 싸움, 침입, 추적/도주, 넘어짐/낙상 | SOP-L4 |
| 5 (매우높음) | 폭력, 방화, 폭발 | SOP-L5 |

**위험도 3 이상** → 알람 자동 생성

---

### 3. 디바이스 프로파일링 + 정합성 재검증

**파일**: `backend/src/total_llm/services/profiling_service.py`

#### 1차 프로파일링

```
[System]
You are a network security device profiler.
Infer the most likely device profile from scan evidence.
Always return strict JSON only.

[User]
Analyze this discovered device and infer profile fields.
Use conservative confidence when evidence is weak.
{스캔 증거 JSON: ip, mac, vendor, open_ports, onvif_info, mdns_info, http_banner, hostname}
```

응답 스키마 (JSON Schema 강제):

```json
{
  "device_type": "CCTV | ACU | ...",
  "manufacturer": "제조사명",
  "model_name": "모델명",
  "protocol": "RTSP | Modbus | ...",
  "confidence": 0.0 ~ 1.0,
  "reasoning": "판단 근거",
  "suggested_device_id": "CCTV-001 등 제안 ID"
}
```

#### 2차 재검증 (정합성 실패 시 자동 실행, 최대 1회)

```
[System]
You are re-verifying a network security device profile.
A previous analysis had inconsistencies with scan evidence.
Re-analyze carefully and correct any mistakes.
Always return strict JSON only.

[User]
Re-analyze this device profile. The previous analysis had inconsistencies.

Scan evidence: {스캔 증거}
Previous profile: {1차 프로파일 결과}
Inconsistencies found:
  device_type: expected CCTV, got ACU (evidence: port 554 open); ...

Please re-analyze considering the scan evidence and the inconsistencies listed above.
Use conservative confidence when evidence is weak.
```

Temperature: `0.1` (결정론적 분류 우선)

---

### 4. Function Calling 채팅 에이전트

**파일**: `backend/src/total_llm/services/tool_agent.py`

도구 모드에서 **2번의 LLM 호출**로 동작합니다.

#### 1차 호출 — 도구 선택

```
[System]
You are a security operations assistant.
When needed, call tools to retrieve exact device/scan data.
Answer in concise Korean unless the user requests another language.

[User]
{사용자 메시지}

[Tools]
- list_devices(status?, device_type?, limit?)
- get_device_health(device_id)
- get_device_health_history(device_id, limit?)
- list_scan_sessions(limit?, status?)
```

#### 2차 호출 — 도구 결과 기반 자연어 응답 (스트리밍)

```
[이전 메시지 히스토리]
+ [Tool] {tool_call_id}: {도구 실행 결과 JSON}
→ LLM이 결과를 해석하여 한국어로 자연스럽게 답변
```

Temperature: `0.1` / vLLM 설정: `--enable-auto-tool-choice --tool-call-parser qwen3_xml`

---

### 5. RAG 자동 시드 (서버 기동 시)

**파일**: `backend/src/total_llm/database/seed.py`

서버 기동 시 `data/documents/` 폴더의 문서를 자동 임베딩·인덱싱합니다.

```
서버 기동 → DB 초기화 → Qdrant 컬렉션 확인 → Embedding 모델 로드
                                                       ↓
                                              seed_documents() 호출
                                                       ↓
                                          data/documents/*.md/*.txt 스캔
                                                       ↓
                                          이미 등록된 파일 건너뜀 (멱등성)
                                                       ↓
                                          새 파일: 500자 청크 분할 → 임베딩
                                                       ↓
                                          Qdrant 인덱싱 + PostgreSQL 메타 저장
```

- 지원 형식: `.md`, `.txt`
- 청크 크기: 500자, 오버랩 50자
- 실패 허용: 개별 파일 오류 시 로그만 남기고 계속 진행 (서버 기동 방해 안 함)

---

## 라이선스

이 프로젝트는 내부 사용 목적으로 개발되었습니다.
