from fastapi import APIRouter

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
