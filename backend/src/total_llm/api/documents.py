from fastapi import APIRouter

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
