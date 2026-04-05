"""End-to-end API test."""
import asyncio, sys, httpx, json
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = 'http://127.0.0.1:18000'

async def test():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # Health check
        h = await c.get('/health')
        print(f'Health: {h.json()}')

        # Login
        r = await c.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
        print(f'Login: {r.status_code}')
        if r.status_code != 200:
            print(r.text)
            return

        token = r.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # Recommendations
        r2 = await c.get('/api/v1/recommendations/feed', headers=headers, params={'size': 5})
        print(f'Recommendations: {r2.status_code}')
        data = r2.json()
        print(f'Strategy: {data.get("strategy_matched")}')
        items = data.get('items', [])
        print(f'Items: {len(items)}')
        for item in items[:3]:
            print(f'  [{item.get("score", "?")}] {item["title"]} — {item["artist_name"]}')

        # Popular tracks
        r3 = await c.get('/api/v1/tracks/popular', params={'limit': 3})
        print(f'\nPopular tracks: {r3.status_code}')
        for track in r3.json()[:3]:
            print(f'  {track["title"]} (plays={track["play_count"]})')

asyncio.run(test())
