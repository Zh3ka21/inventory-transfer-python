from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db, repository
from app.rules import check_transfer_allowed

router = APIRouter(prefix="/api")


class TransferRequest(BaseModel):
    sku: str
    from_location: str = Field(alias="fromLocation")
    to_location: str = Field(alias="toLocation")
    quantity: int


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


@router.get("/health")
async def health():
    return {"status": "UP", "pool": db.pool_stats()}


@router.get("/inventory/{sku}")
async def get_inventory(sku: str):
    async with db.connection() as conn:
        levels = await repository.get_stock_levels(conn, sku)

    if not levels:
        return error(404, f"unknown SKU {sku}")
    return {
        "sku": sku,
        "locations": [{"location": loc, "quantity": qty} for loc, qty in levels.items()],
        "total": sum(levels.values()),
    }


@router.post("/transfer")
async def transfer(req: TransferRequest):
    conn = await db.getconn()

    try:
        levels = await repository.get_stock_levels(conn, req.sku)
        if not levels:
            return error(404, f"unknown SKU {req.sku}")
        for location in (req.from_location, req.to_location):
            if location not in levels:
                return error(404, f"{req.sku} is not stocked at {location}")

        problem = await check_transfer_allowed(
            req.sku, req.from_location, req.to_location, req.quantity
        )
        if problem:
            return error(400, problem)

        available = levels[req.from_location]
        if available < req.quantity:
            message = (
                f"insufficient stock at {req.from_location}: "
                f"available {available}, requested {req.quantity}"
            )
            return error(400, message)

        await repository.move_stock(conn, req.sku, req.from_location, req.to_location, req.quantity)

        return {
            "status": "COMPLETED",
            "sku": req.sku,
            "fromLocation": req.from_location,
            "toLocation": req.to_location,
            "quantity": req.quantity,
        }
    finally:
        await db.putconn(conn)
