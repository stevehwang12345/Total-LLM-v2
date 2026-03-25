from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
