from fastapi import APIRouter

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
