"""Quick DB status check."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async def check():
    e = create_async_engine("mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec")
    s = async_sessionmaker(e, class_=AsyncSession)()
    r = await s.execute(text("SELECT COUNT(*) FROM tracks"))
    print(f"Tracks: {r.scalar()}")
    r = await s.execute(text("SELECT COUNT(*) FROM users"))
    print(f"Users: {r.scalar()}")
    r = await s.execute(text("SELECT COUNT(*) FROM user_interactions"))
    print(f"Interactions: {r.scalar()}")
    await s.close()
    await e.dispose()

asyncio.run(check())
