from fastapi import APIRouter

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
