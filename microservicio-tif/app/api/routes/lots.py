from fastapi import APIRouter

router = APIRouter(tags=["lots"])


@router.get("/lots/{lot_id}/results")
async def get_lot_results(lot_id: int):
    return {"status": "not_implemented", "lot_id": lot_id}
