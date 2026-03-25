from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    use_rag: bool = True


class ChatStreamEvent(BaseModel):
    content: str
    conversation_id: str
    done: bool = False


class AnalysisRequest(BaseModel):
    image_base64: str
    location: str | None = None


class AnalysisResult(BaseModel):
    qa_results: dict
    incident_type: str
    severity: str
    confidence: float
    report: str


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
    created_at: datetime


class ReportModel(BaseModel):
    report_id: str
    title: str
    created_at: datetime
    download_url: str
