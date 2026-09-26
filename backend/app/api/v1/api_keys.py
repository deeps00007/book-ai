from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.services import api_key_pool

router = APIRouter()


class AddKeyRequest(BaseModel):
    api_key: str
    label: str = ""
    provider: str = "fireworks"


@router.post("/api-keys")
async def add_key(
    req: AddKeyRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if len(req.api_key) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    result = await api_key_pool.add_api_key(db, user.id, req.api_key, req.label, req.provider)
    return result


@router.get("/api-keys")
async def list_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    keys = await api_key_pool.list_api_keys(db, user.id)
    active_count = sum(1 for k in keys if k["status"] == "active")
    return {"keys": keys, "active_count": active_count}


@router.delete("/api-keys/{key_id}")
async def delete_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await api_key_pool.delete_api_key(db, key_id, user.id)
    return {"ok": True}
