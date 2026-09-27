from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health")
async def health(session: Session) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
