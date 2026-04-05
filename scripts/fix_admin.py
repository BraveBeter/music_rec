import asyncio, sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def insert():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from passlib.context import CryptContext
    engine = create_async_engine('mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec')
    sf = async_sessionmaker(engine, class_=AsyncSession)
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto', bcrypt__rounds=12)
    admin_hash = pwd_context.hash('admin123')
    async with sf() as s:
        res = await s.execute(text("SELECT user_id FROM users WHERE username = 'admin'"))
        if not res.first():
            await s.execute(
                text("INSERT INTO users (username, password_hash, role, age, gender, country) VALUES ('admin', :pwd, 'admin', 25, 1, 'China')"),
                {"pwd": admin_hash}
            )
            await s.commit()
            print('Admin user inserted')
        else:
            print('Admin already exists')
    await engine.dispose()

asyncio.run(insert())
