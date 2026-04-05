import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
async def update():
    engine = create_async_engine('mysql+aiomysql://music_app:music_app_pass_2026@musicrec_mysql:3306/music_rec')
    async with engine.begin() as conn:
        await conn.execute(text('UPDATE users SET password_hash = ''$2b$12$iIr5ocgmGsKOhOG4/Ke4AuXeaFukrV/QQ9N2dhjATHvHlT3ERecz46'' WHERE username LIKE ''synth_user_%%'''))
    await engine.dispose()
asyncio.run(update())
