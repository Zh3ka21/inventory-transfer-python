from psycopg import AsyncConnection


class ErrorInsufficientStock(Exception):
    pass


async def get_stock_levels(conn: AsyncConnection, sku: str) -> dict[str, int]:
    cur = await conn.execute(
        "SELECT location, quantity FROM inventory WHERE sku = %s ORDER BY location",
        (sku,),
    )
    return {location: quantity for location, quantity in await cur.fetchall()}


async def get_quantity(conn: AsyncConnection, sku: str, location: str) -> int:
    cur = await conn.execute(
        "SELECT quantity FROM inventory WHERE sku = %s AND location = %s",
        (sku, location),
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError(f"{sku} is not stocked at {location}")
    return row[0]


async def set_quantity(conn: AsyncConnection, sku: str, location: str, quantity: int) -> None:
    await conn.execute(
        "UPDATE inventory SET quantity = %s, updated_at = now() WHERE sku = %s AND location = %s",
        (quantity, sku, location),
    )


async def move_stock(conn, sku, from_location, to_location, quantity):
    async with conn.transaction():
        cur = await conn.execute(
                "SELECT location, quantity FROM inventory "
                "WHERE sku = %s AND location IN (%s, %s) ORDER BY location FOR UPDATE",
                (sku, from_location, to_location),
        )
        rows = dict(await cur.fetchall())
        for loc in (from_location, to_location):
            if loc not in rows:
                raise LookupError(f"{sku} is not stocked at {loc}")
        if rows[from_location] < quantity:
            raise ErrorInsufficientStock(
                f"insufficient stock at {from_location}: "
                f"available {rows[from_location]}, requested {quantity}"
            )
        await conn.execute(
            "UPDATE inventory SET quantity = quantity - %s, updated_at = now() "
            "WHERE sku = %s AND location = %s", (quantity, sku, from_location))
        await conn.execute(
            "UPDATE inventory SET quantity = quantity + %s, updated_at = now() "
            "WHERE sku = %s AND location = %s", (quantity, sku, to_location))

