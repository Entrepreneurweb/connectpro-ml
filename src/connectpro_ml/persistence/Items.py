from fastapi import APIRouter, Depends, HTTPException, status
from asyncpg import Connection
from pydantic import BaseModel
 
#from app.database import db_dependency
from connectpro_ml.persistence.Database import db_dependency
 
router = APIRouter(prefix="/items", tags=["items"])
 
 
# ── Schémas ───────────────────────────────────────────────────────────────
 
class ItemCreate(BaseModel):
    name: str
    category: str | None = None
 
 
class ItemResponse(BaseModel):
    id: int
    name: str
    category: str | None
 
 
# ── Endpoints ─────────────────────────────────────────────────────────────
 
@router.get("/", response_model=list[ItemResponse])
async def list_items(conn: Connection = Depends(db_dependency)):
    rows = await conn.fetch("SELECT id, name, category FROM items ORDER BY id")
    return [dict(r) for r in rows]
 
 
@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, conn: Connection = Depends(db_dependency)):
    row = await conn.fetchrow("SELECT id, name, category FROM items WHERE id = $1", item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item introuvable.")
    return dict(row)
 
 
@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(body: ItemCreate, conn: Connection = Depends(db_dependency)):
    row = await conn.fetchrow(
        "INSERT INTO items (name, category) VALUES ($1, $2) RETURNING id, name, category",
        body.name, body.category,
    )
    return dict(row)
 
 
@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, conn: Connection = Depends(db_dependency)):
    result = await conn.execute("DELETE FROM items WHERE id = $1", item_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Item introuvable.")