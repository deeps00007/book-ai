from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.services import usage_service

router = APIRouter()


@router.get("/usage/summary")
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await usage_service.get_summary(db, user.id, days)


@router.get("/usage/daily")
async def usage_daily(
    days: int = Query(14, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await usage_service.get_daily(db, user.id, days)


@router.get("/usage/by-model")
async def usage_by_model(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await usage_service.get_by_model(db, user.id, days)
