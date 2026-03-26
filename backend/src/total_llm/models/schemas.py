from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    use_rag: bool = True
    use_tools: bool = False


class ChatStreamEvent(BaseModel):
    content: str
    conversation_id: str
    done: bool = False


class AnalysisRequest(BaseModel):
    image_base64: str
    location: str | None = None


class AnalysisResult(BaseModel):
    qa_results: dict = {}
    incident_type: str = "정상활동"
    incident_type_en: str = "Normal"
    severity: str = "정보"
    risk_level: int = 1
    confidence: float = 0.5
    report: str = ""
    recommended_actions: list[str] = []
    sop_reference: str | None = None
    location: str | None = None
    timestamp: datetime | None = None
    summary: str = ""
    description: str = ""
    media_type: str = "image"


class DeviceModel(BaseModel):
    device_id: str
    device_type: str
    manufacturer: str
    ip_address: str
    port: int
    protocol: str
    location: str
    status: str


class AlarmModel(BaseModel):
    alarm_id: str
    device_id: str
    severity: str
    description: str
    timestamp: datetime
    acknowledged: bool = False


class DocumentModel(BaseModel):
    doc_id: str
    filename: str
    size: int
    chunk_count: int = 0
    created_at: datetime


class ReportModel(BaseModel):
    report_id: str
    title: str
    type: str = "security"
    created_at: datetime
    download_url: str
