from fastapi import APIRouter

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
