from fastapi import APIRouter

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
