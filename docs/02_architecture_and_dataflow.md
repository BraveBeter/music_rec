# 2. 宏观架构与数据流 (Architecture & Data Flow)

## 2.1 系统架构解析

### 整体分层

系统采用**前后端分离 + ML 管线旁路 + 独立管理端**的架构，分为以下 6 个独立层级：

```
┌─────────────────────────────────────────────────────────────┐
│                     用户浏览器 (Browser)                      │
│  Vue 3 SPA · Pinia Store · HTML5 Audio · Axios HTTP Client  │
└────────────┬───────────────────────────────┬────────────────┘
             │ HTTP (REST API)               │ Audio Stream
             │ /api/v1/*                     │ /api/v1/tracks/{id}/preview
             ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Vite Dev Server (Port 13000)                │
│         反向代理: /api → Backend:8000                        │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Port 18000)                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Auth API │  │Track API │  │Interact   │  │Recommend  │  │
│  │ /auth/*  │  │/tracks/* │  │API        │  │API        │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  │
│       │              │              │              │         │
│  ┌────▼──────────────▼──────────────▼──────────────▼─────┐  │
│  │              Service Layer (业务逻辑层)                 │  │
│  │  auth_service · track_service · interaction_service    │  │
│  │              recommendation_service                    │  │
│  └────┬──────────────┬──────────────┬────────────────────┘  │
│       │              │              │                        │
│  ┌────▼─────┐  ┌─────▼──────┐  ┌───▼────────────────────┐  │
│  │  MySQL   │  │   Redis    │  │   ML Pipeline (推理)    │  │
│  │  (ORM)   │  │  (Cache)   │  │  recall → ranking      │  │
│  └──────────┘  └────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │               │                  │
         ▼               ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐
│ MySQL 8.0    │ │ Redis 7      │ │ ML Pipeline (离线训练)    │
│ Port 13307   │ │ Port 16379   │ │ data_process → training  │
│ 7张核心表    │ │ 用户序列缓存 │ │ → 模型文件保存到磁盘      │
│              │ │ 推荐结果缓存 │ │ inference 时被 Backend    │
│              │ │              │ │ 动态 import 调用          │
└──────────────┘ └──────────────┘ └──────────────────────────┘
```

### 各层职责

| 层级 | 组件 | 职责 | 通信方式 |
|------|------|------|----------|
| **前端展示层** | Vue 3 SPA | 页面渲染、用户交互、播放器控制、收藏状态管理 | HTTP REST → Vite Proxy → Backend |
| **API 网关层** | Vite Dev Server | 开发环境反向代理，将 `/api/*` 转发到 Backend，解决跨域 | HTTP Proxy |
| **后端服务层** | FastAPI | 接收请求、参数校验、鉴权、调用 Service、返回 JSON | 内部函数调用 |
| **业务逻辑层** | Service Classes | 认证逻辑、交互记录、推荐编排（4 级降级策略） | SQLAlchemy → MySQL；aioredis → Redis；import → ML Pipeline |
| **数据存储层** | MySQL + Redis | MySQL 存储全部持久化数据；Redis 缓存推荐结果和用户播放序列 | TCP 直连 |

### ML 管线与后端的关系

ML Pipeline 不是独立服务，而是作为 Python 包被 Backend **动态 import** 使用：

```
Backend 推荐请求到达
  → recommendation_service.get_recommendations()
    → _ml_pipeline_recommend()
      → from ml_pipeline.inference.pipeline import recommend  # 动态导入
        → recall.py:  多路召回（ItemCF + SASRec + Popularity）
        → ranking.py: DeepFM 精排
      ← 返回 [{track_id, score}, ...]
    → cache_recommendations() 写入 Redis
  ← 返回 JSON 给前端
```

如果 ML Pipeline 的模型文件不存在（`data/models/` 下无 `meta.json`），`ImportError` 会被捕获，系统自动降级到离线推荐或热门兜底，**不会崩溃**。

---

## 2.2 核心业务流转

### 场景一：用户登录并获取个性化推荐（完整闭环）

这是系统最核心的业务流程，从用户打开浏览器到看到推荐列表：

```
[1] 用户打开浏览器 → http://localhost:13000
    │
    ▼
[2] Vue Router 加载 Home.vue
    │  onMounted() 同时发起两个并行请求:
    │  ├── recommendationsApi.getFeed({ size: 20 })
    │  └── tracksApi.popular(10)
    │
    ▼
[3] Axios 发出 GET /api/v1/recommendations/feed?size=20
    │  请求经过 client.ts 拦截器:
    │  - 如果 localStorage 有 access_token，注入 Authorization: Bearer <token>
    │  - 如果没有 token（未登录），不注入 Header
    │
    ▼
[4] Vite Dev Server 代理 /api → http://musicrec_backend:8000
    │
    ▼
[5] FastAPI 路由匹配: recommendations.py → get_feed()
    │  参数: size=20, scene="home_feed", current_track_id=None
    │  依赖注入: get_current_user_optional → 尝试解析 token
    │    - 有 token 且有效 → current_user = User 对象
    │    - 无 token 或无效 → current_user = None
    │
    ▼
[6] recommendation_service.get_recommendations(db, user_id, size=20)
    │
    │  ┌─ 策略 1: Redis 缓存 ──────────────────────────────┐
    │  │  redis.get("rec:user:{user_id}")                    │
    │  │  命中 → 反序列化 JSON → 直接返回 (TTL=30分钟)       │
    │  └───────────────────────────────────────────────────┘
    │  │ 未命中
    │  ▼
    │  ┌─ 策略 2: ML Pipeline 推理 ────────────────────────┐
    │  │  _ml_pipeline_recommend(db, user_id, size=20)       │
    │  │    │                                                │
    │  │    │ [a] 获取用户播放序列                            │
    │  │    │   redis.lrange("user:seq:{user_id}", 0, 49)    │
    │  │    │   → ["DZ12345", "DZ67890", ...] 最近50首      │
    │  │    │                                                │
    │  │    │ [b] 获取热门歌曲作为兜底召回源                   │
    │  │    │   get_popular_tracks(db, limit=50)              │
    │  │    │                                                │
    │  │    │ [c] 调用 ML Pipeline                           │
    │  │    │   ml_recommend(                                 │
    │  │    │     user_id=42,                                 │
    │  │    │     user_sequence=["DZ123","DZ456",...],        │
    │  │    │     popular_tracks=[{...},...],                 │
    │  │    │     top_k=20                                    │
    │  │    │   )                                             │
    │  │    │     │                                           │
    │  │    │     ├── Step 1: 多路召回 (recall.py)            │
    │  │    │     │   ├── SASRec: 基于序列预测下一首           │
    │  │    │     │   │   输入: ["DZ123","DZ456",...]         │
    │  │    │     │   │   输出: [(track_id, score), ...] top 150 │
    │  │    │     │   │                                       │
    │  │    │     │   ├── ItemCF: 基于相似物品推荐             │
    │  │    │     │   │   输入: user_id=42                    │
    │  │    │     │   │   查找用户历史交互 → 找相似歌曲       │
    │  │    │     │   │   输出: [(track_id, score), ...] top 150 │
    │  │    │     │   │                                       │
    │  │    │     │   └── Popularity: 热门歌曲补充             │
    │  │    │     │       分数 = 1/(排名+1)，权重 0.3         │
    │  │    │     │                                           │
    │  │    │     │   合并去重: SASRec结果+SASRec∩ItemCF加权  │
    │  │    │     │   → candidates: {track_id: (score, src)} │
    │  │    │     │   → 返回最多 350 个候选                   │
    │  │    │     │                                           │
    │  │    │     └── Step 2: DeepFM 精排 (ranking.py)        │
    │  │    │         输入: user_id + 350个候选track_id       │
    │  │    │         │                                       │
    │  │    │         │ 构建特征矩阵:                          │
    │  │    │         │   sparse: [user_idx, track_idx,       │
    │  │    │         │           age_bucket, gender,         │
    │  │    │         │           country_idx] × 350行        │
    │  │    │         │   dense: [interaction_count,          │
    │  │    │         │          play_count, ...,             │
    │  │    │         │          danceability, energy, ...]   │
    │  │    │         │           × 350行                     │
    │  │    │         │                                       │
    │  │    │         │ DeepFM 推理:                          │
    │  │    │         │   output = sigmoid(linear + FM + DNN) │
    │  │    │         │   分数融合: 70% DeepFM + 30% 召回分   │
    │  │    │         │                                       │
    │  │    │         → 返回 top 20: [(track_id, score), ...] │
    │  │    │                                                │
    │  │    │ [d] 用 DB 数据丰富结果                          │
    │  │    │   _fetch_tracks_by_ids(db, track_ids)           │
    │  │    │   → 补全 title, artist_name, cover_url 等      │
    │  │    │                                                │
    │  │    │ [e] 缓存到 Redis (TTL=30分钟)                  │
    │  │    │   redis.setex("rec:user:42", 1800, JSON)       │
    │  │    └────────────────────────────────────────────────┘
    │  │ ML Pipeline 失败或无模型 ↓
    │  ▼
    │  ┌─ 策略 3: 离线预计算 ──────────────────────────────┐
    │  │  SELECT recommended_track_ids                       │
    │  │  FROM offline_recommendations WHERE user_id=42      │
    │  │  → 取 JSON 数组中的 track_id → 查 DB 补全信息      │
    │  └───────────────────────────────────────────────────┘
    │  │ 无离线数据 ↓
    │  ▼
    │  ┌─ 策略 4: 热门兜底 ────────────────────────────────┐
    │  │  get_popular_tracks(db, limit=20)                   │
    │  │  → SELECT * FROM tracks ORDER BY play_count DESC    │
    │  │  → 无需登录，任何用户都能获得                       │
    │  └───────────────────────────────────────────────────┘
    │
    ▼
[7] 返回 JSON 给前端:
    {
      "strategy_matched": "sasrec_deepfm",
      "is_fallback": false,
      "items": [
        {
          "track_id": "DZ12345",
          "title": "Blinding Lights",
          "artist_name": "The Weeknd",
          "album_name": "After Hours",
          "duration_ms": 200000,
          "preview_url": "https://cdnt-preview.dzcdn.net/...",
          "cover_url": "https://e-cdns-images.dzcdn.net/...",
          "score": 0.8742
        },
        ... 共 20 首
      ]
    }
    │
    ▼
[8] Home.vue 渲染推荐卡片
    │  v-for 遍历 recommendations 数组
    │  每首歌渲染为 <TrackCard>
    │  - 显示封面图 (cover_url)
    │  - 显示标题、歌手
    │  - 显示推荐分数 (score * 100 取整)
    │  - 点击 → player.play(track) 触发播放
    │
    ▼
[9] 用户点击某首歌 → player store.play(track, tracks)
    │  构建 proxy URL: /api/v1/tracks/DZ12345/preview
    │  audio.src = proxy URL
    │  audio.play()
    │
    ▼
[10] Backend 代理音频流: tracks.py → proxy_preview()
     │  从 track_id 提取 Deezer 数字 ID (去掉 "DZ" 前缀)
     │  调用 Deezer API: GET https://api.deezer.com/track/{id}
     │  获取最新的签名 preview URL (含 hdnea token)
     │  用 httpx 流式下载 CDN 音频 → 8192 bytes 分块回传浏览器
     │  Content-Type: audio/mpeg
     │
     ▼
[11] 歌曲播放结束 → player store 触发 ended 事件
     │  logPlayInteraction():
     │    POST /api/v1/interactions
     │    {
     │      "track_id": "DZ12345",
     │      "interaction_type": 1,       // play
     │      "play_duration": 198500,     // ms
     │      "client_timestamp": 1712289600
     │    }
     │
     ▼
[12] Backend 记录交互: interaction_service.log_interaction()
     │  计算 completion_rate = play_duration / duration_ms = 198500/200000 = 0.9925
     │  写入 MySQL user_interactions 表
     │  更新 tracks.play_count += 1
     │  Redis lpush "user:seq:42" → ["DZ12345", ...] (滑动窗口, 最大50首, TTL=7天)
     │
     ▼
[13] 下次请求推荐时，新的播放记录已进入 SASRec 序列
     → 推荐结果将反映最新的用户偏好
```

### 场景二：用户注册与鉴权流程

```
[1] 用户填写注册表单 (Register.vue)
    │  username, password, confirmPassword, age?, gender?, country?
    │
    ▼
[2] 前端校验: 用户名非空、密码>=6字符、两次密码一致
    │
    ▼
[3] POST /api/v1/auth/register
    │  Body: { username: "alice", password: "pass123", age: 25, gender: 2, country: "China" }
    │
    ▼
[4] auth.py → register()
    │  auth_service.register_user(db, "alice", "pass123", age=25, ...)
    │    │
    │    ├── 检查用户名是否已存在: SELECT FROM users WHERE username="alice"
    │    │  已存在 → 抛出 ValueError("Username already exists") → HTTP 400
    │    │
    │    ├── 密码哈希: pwd_context.hash("pass123") → "$2b$12$..."
    │    │
    │    └── INSERT INTO users (username, password_hash, role, age, gender, country)
    │       → user_id = 自增ID (例如 43)
    │
    ▼
[5] 生成 JWT 双令牌:
    │  generate_tokens(user)
    │    ├── access_token:  jwt.encode({"sub": "43", "exp": now+15min, "type": "access"})
    │    └── refresh_token: jwt.encode({"sub": "43", "exp": now+7天, "type": "refresh"})
    │
    ▼
[6] 返回响应:
    │  Body: { access_token: "eyJ...", user_id: 43, username: "alice", role: "user" }
    │  Set-Cookie: refresh_token=eyJ...; HttpOnly; Path=/api/v1/auth; Max-Age=604800; SameSite=Lax
    │
    ▼
[7] 前端 auth store 处理:
    │  setAuth(token, userInfo):
    │    localStorage.setItem('access_token', token)
    │    localStorage.setItem('user_info', JSON.stringify({user_id, username, role, ...}))
    │  自动加载收藏列表: useFavoritesStore().loadFavorites()
    │
    ▼
[8] 后续请求自动携带 Token:
    │  Axios 拦截器 (client.ts):
    │    request interceptor → 读取 auth.accessToken → 注入 Authorization Header
    │    response interceptor → 401 → 自动调用 /auth/refresh → 用 Cookie 中的 refresh_token 换新 access_token
    │                           → 刷新失败 → auth.logout() 清空状态 → 跳转 /login
```

---

## 2.3 推荐 4 级降级策略详解

推荐系统采用 4 级降级保证高可用，每一级都是上一级的兜底：

| 级别 | 策略名称 | 数据源 | 延迟 | 适用条件 |
|------|---------|--------|------|---------|
| L1 | Redis 缓存命中 | Redis `rec:user:{id}` | <1ms | 30分钟内重复请求 |
| L2 | ML Pipeline 实时推理 | Redis序列 + 磁盘模型 + MySQL | 100-500ms | 有登录用户 + 模型文件存在 |
| L3 | 离线预计算 | MySQL `offline_recommendations` 表 | 10-50ms | 有登录用户 + 离线表有数据 |
| L4 | 热门兜底 | MySQL `tracks` 表 (ORDER BY play_count) | 5-20ms | 所有场景（包括匿名用户） |

L2 内部还有子降级：
- 有 SASRec 模型 + 用户序列>=3 → `sasrec_deepfm` 或 `sasrec_only`
- 有 ItemCF 模型 → `itemcf_deepfm` 或 `itemcf_only`
- 无任何模型 → 直接跳到 L3/L4
- DeepFM 排序失败 → 使用召回分数直接排序
