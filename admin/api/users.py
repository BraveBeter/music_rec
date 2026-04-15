"""Admin users — batch import."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from pydantic import BaseModel
from typing import Optional

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


class UserItem(BaseModel):
    username: str
    password_hash: str
    age: Optional[int] = None
    gender: Optional[int] = None
    country: Optional[str] = None


class BatchUserRequest(BaseModel):
    users: list[UserItem]
    default_role: str = "user"


@router.post("/batch")
async def batch_insert_users(
    req: BatchUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Batch insert users."""
    inserted = 0
    skipped = 0

    for u in req.users:
        result = await db.execute(select(User).where(User.username == u.username))
        if result.scalar_one_or_none():
            skipped += 1
            continue

        await db.execute(text("""
            INSERT IGNORE INTO users (username, password_hash, role, age, gender, country)
            VALUES (:username, :password_hash, :role, :age, :gender, :country)
        """), {
            "username": u.username,
            "password_hash": u.password_hash,
            "role": req.default_role,
            "age": u.age,
            "gender": u.gender,
            "country": u.country,
        })
        inserted += 1

    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total": len(req.users)}
