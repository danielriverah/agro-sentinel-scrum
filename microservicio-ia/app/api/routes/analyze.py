from fastapi import APIRouter

router = APIRouter(tags=["analyze"])


@router.post("/analyze", status_code=202)
async def analyze():
    return {"status": "not_implemented"}
