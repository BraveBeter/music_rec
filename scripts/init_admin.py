"""
Minimal init script: creates the admin account only.
Tables are created by init.sql (MySQL entrypoint).
Run this as the seeder — nothing else.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


async def init_admin():
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if admin already exists
        result = await session.execute(
            text("SELECT user_id FROM users WHERE username = :username"),
            {"username": ADMIN_USERNAME},
        )
        if result.first():
            print(f"Admin user '{ADMIN_USERNAME}' already exists. Skipping.")
            await engine.dispose()
            return

        # Create admin
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
        admin_hash = pwd_context.hash(ADMIN_PASSWORD)

        await session.execute(
            text("""
                INSERT INTO users (username, password_hash, role, age, gender, country)
                VALUES (:username, :password_hash, :role, :age, :gender, :country)
            """),
            {
                "username": ADMIN_USERNAME,
                "password_hash": admin_hash,
                "role": "admin",
                "age": 25,
                "gender": 1,
                "country": "China",
            },
        )
        await session.commit()
        print(f"Created admin user: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_admin())
