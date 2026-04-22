# 4. 核心枢纽模块深度拆解 (Core Modules Deep Dive)

## 4.1 配置文件/环境脚手架

### 4.1.1 `app/config.py` — 应用配置中心

```python
class Settings(BaseSettings):
    APP_NAME: str = "MusicRec"              # 应用名称
    APP_ENV: str = "development"            # 环境：development / production
    APP_DEBUG: bool = True                  # 调试模式：控制 SQLAlchemy echo 和日志级别

    MYSQL_HOST: str = "localhost"           # MySQL 主机（Docker 内部为 musicrec_mysql）
    MYSQL_PORT: int = 13307                 # MySQL 端口（Docker 内部为 3306）
    MYSQL_USER: str = "music_app"           # 数据库用户名
    MYSQL_PASSWORD: str = "music_app_pass_2026"  # 数据库密码
    MYSQL_DATABASE: str = "music_rec"       # 数据库名

    REDIS_HOST: str = "localhost"           # Redis 主机
    REDIS_PORT: int = 16379                 # Redis 端口（Docker 内部为 6379）
    REDIS_PASSWORD: str = "redis_music_2026" # Redis 密码

    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-2026"  # JWT 签名密钥
    JWT_ALGORITHM: str = "HS256"            # JWT 算法
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15   # Access Token 有效期：15 分钟
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7      # Refresh Token 有效期：7 天
```

**关键计算属性**：
- `DATABASE_URL` → `mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec`（异步连接串）
- `DATABASE_URL_SYNC` → `mysql+pymysql://...`（同步连接串，ML 管线使用）
- `REDIS_URL` → `redis://:redis_music_2026@localhost:16379/0`

**配置加载优先级**：`.env` 先加载 → `.env.local` 后加载覆盖（本地开发用 `.env.local` 覆盖 Docker 专用配置）。`get_settings()` 用 `@lru_cache()` 装饰，全局单例。

### 4.1.2 `docker-compose.yml` — 容器编排

**5 个服务容器**：

| 服务 | 镜像 | 端口映射 | 启动条件 | 关键配置 |
|------|------|---------|---------|---------|
| `musicrec_mysql` | mysql:8.0 | 13307:3306 | 无 | `--character-set-server=utf8mb4`；挂载 `init.sql` 为自动初始化脚本；healthcheck 用 `mysqladmin ping` |
| `musicrec_redis` | redis:7-alpine | 16379:6379 | 无 | `redis-server --requirepass ${REDIS_PASSWORD}`；healthcheck 用 `redis-cli ping` |
| `musicrec_backend` | 自建 (Python) | 18000:8000 | MySQL healthy + Redis healthy | 环境变量覆盖 HOST/PORT 为 Docker 内部名；挂载 `app/`、`ml_pipeline/`、`data/` 实现热重载 |
| `musicrec_seeder` | 自建 (Python) | 无 | MySQL healthy | `command: bash -c "python scripts/seed_data.py && python ml_pipeline/data_process/generate_synthetic_data.py"`；运行后退出 |
| `musicrec_frontend` | 自建 (Node) | 13000:3000 | backend 启动 | `VITE_API_PROXY_TARGET=http://musicrec_backend:8000`；挂载 `src/` 热重载 |

**网络**：所有服务在 `musicrec_net` bridge 网络中，通过 Docker 内部 hostname 通信（如 `musicrec_mysql:3306`）。

**数据卷**：`musicrec_mysql_data` 和 `musicrec_redis_data` 命名卷持久化数据，容器重建不丢失。

### 4.1.3 `app/Dockerfile` — 后端镜像

```dockerfile
FROM python:3.11-slim
# 安装 gcc + mysql 客户端库（编译 aiomysql/cryptography 需要）
RUN apt-get update && apt-get install -y gcc default-libmysqlclient-dev pkg-config
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 4.1.4 `frontend/Dockerfile` — 前端镜像

```dockerfile
FROM node:20-alpine
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
```

### 4.1.5 `ml_pipeline/config.py` — ML 超参数

| 常量 | 值 | 用途 |
|------|---|------|
| `EMBEDDING_DIM` | 64 | 所有模型的 Embedding 维度 |
| `HIDDEN_DIMS` | [256, 128, 64] | DeepFM DNN 隐藏层维度 |
| `LEARNING_RATE` | 1e-3 | 所有模型的默认学习率 |
| `BATCH_SIZE` | 256 | 默认批大小 |
| `EPOCHS` | 20 | 默认训练轮数 |
| `MAX_SEQ_LEN` | 50 | SASRec 最大序列长度 / Redis 滑动窗口大小 |
| `TOP_K` | 20 | 默认推荐返回数量 |
| `NEG_SAMPLE_RATIO` | 4 | DeepFM 负采样比例（1正:4负） |
| `COMPLETION_RATE_THRESHOLD` | 0.3 | 隐式标签阈值：completion < 0.3 视为负样本 |

### 4.1.6 `frontend/vite.config.ts` — 前端构建配置

```typescript
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },  // @ → src/
  },
  server: {
    port: 13000,           // 开发服务器端口
    host: '0.0.0.0',      // 允许外部访问（Docker 需要）
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:18000',
        changeOrigin: true,   // 代理所有 /api/* 请求到后端
      },
    },
  },
})
```

---

## 4.2 入口与路由

### 4.2.1 后端启动入口 `app/main.py`

```
启动顺序：
1. Settings 单例初始化（读取 .env）
2. logging.basicConfig（DEBUG/INFO 根据 APP_DEBUG）
3. @asynccontextmanager lifespan：
   - startup: 打印日志
   - shutdown: close_redis() 关闭 Redis 连接
4. FastAPI() 实例化，注册 lifespan
5. CORS 中间件：允许 localhost:13000/18000/3000 的跨域请求
6. register_exception_handlers(app)：全局异常 → 统一 JSON 格式 {code, msg, data}
7. 注册 6 个 Router，前缀 /api/v1：
   - auth_router    → /api/v1/auth/*
   - users_router   → /api/v1/users/*
   - tracks_router  → /api/v1/tracks/*
   - interactions_router → /api/v1/interactions
   - recommendations_router → /api/v1/recommendations/feed
   - favorites_router → /api/v1/favorites/*
8. /health 健康检查端点
```

### 4.2.2 完整 API 路由表

| 方法 | 路径 | 认证 | 处理函数 | 输入 | 输出 |
|------|------|------|---------|------|------|
| POST | `/api/v1/auth/register` | 无 | `register()` | `{username, password, age?, gender?, country?}` | `{access_token, user_id, username, role}` + Set-Cookie |
| POST | `/api/v1/auth/login` | 无 | `login()` | `{username, password}` | `{access_token, user_id, username, role}` + Set-Cookie |
| POST | `/api/v1/auth/refresh` | Cookie | `refresh_token()` | Cookie: refresh_token | `{access_token}` |
| POST | `/api/v1/auth/logout` | 无 | `logout()` | 无 | 清除 Cookie |
| GET | `/api/v1/users/me` | 必须 | `get_profile()` | 无 | `{user_id, username, role, age, gender, country, created_at}` |
| PUT | `/api/v1/users/me/profile` | 必须 | `update_profile()` | `{age?, gender?, country?}` | 更新后的 UserProfile |
| GET | `/api/v1/users/me/stats` | 必须 | `get_stats()` | 无 | `{play_count, favorites_count, days_registered}` |
| GET | `/api/v1/users/me/favorites/ids` | 必须 | `get_favorite_ids()` | 无 | `{track_ids: string[]}` |
| GET | `/api/v1/tracks` | 无 | `list_tracks()` | `?query=&page=1&page_size=20` | `{items, total, page, page_size}` |
| GET | `/api/v1/tracks/popular` | 无 | `popular_tracks()` | `?limit=20` | `Track[]` |
| GET | `/api/v1/tracks/{track_id}` | 无 | `get_track()` | path: track_id | `TrackResponse` |
| GET | `/api/v1/tracks/{track_id}/preview` | 无 | `proxy_preview()` | path: track_id | StreamingResponse (audio/mpeg) |
| POST | `/api/v1/interactions` | 必须 | `create_interaction()` | `{track_id, interaction_type(1-4), rating?, play_duration?}` | `{interaction_id}` |
| GET | `/api/v1/interactions/history` | 必须 | `interaction_history()` | `?limit=50` | `InteractionResponse[]` |
| GET | `/api/v1/recommendations/feed` | 可选 | `get_feed()` | `?size=20&scene=home_feed&current_track_id=` | `{strategy_matched, is_fallback, items}` |
| GET | `/api/v1/favorites` | 必须 | `list_favorites()` | 无 | `TrackResponse[]` |
| POST | `/api/v1/favorites/{track_id}` | 必须 | `add_favorite()` | path: track_id | `{code, msg}` |
| DELETE | `/api/v1/favorites/{track_id}` | 必须 | `remove_favorite()` | path: track_id | `{code, msg}` |

### 4.2.3 前端路由 `router/index.ts`

| 路径 | 组件 | meta | 说明 |
|------|------|------|------|
| `/` | `Home.vue` | 无 | 首页：推荐 + 热门 |
| `/login` | `Login.vue` | `{guest: true}` | 仅未登录可访问 |
| `/register` | `Register.vue` | `{guest: true}` | 仅未登录可访问 |
| `/discover` | `Discover.vue` | 无 | 搜索浏览曲库 |
| `/profile` | `Profile.vue` | `{requiresAuth: true}` | 需登录 |
| `/favorites` | `Favorites.vue` | `{requiresAuth: true}` | 需登录 |

**导航守卫逻辑**：`beforeEach` 检查 `localStorage.getItem('access_token')`，有 token 则已登录态。`requiresAuth` 路由无 token → 重定向 `/login?redirect=原始路径`；`guest` 路由有 token → 重定向 `/`。

### 4.2.4 管理后端 API 路由表 (`admin/`)

#### 认证与状态

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| POST | `/admin/auth/login` | 无 | 管理员登录（role='admin'校验） |
| GET | `/admin/status` | 必须 | 系统状态统计（用户/歌曲/交互数/模型状态） |

#### 数据管理

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| POST | `/admin/data/jamendo` | 必须 | 导入 Jamendo 数据 |
| POST | `/admin/data/deezer` | 必须 | 导入 Deezer 数据 |
| POST | `/admin/data/lastfm` | 必须 | 生成 LastFM 1K 用户数据 |
| POST | `/admin/data/synthetic` | 必须 | 生成合成 60 用户数据 |
| POST | `/admin/users/batch` | 必须 | 批量导入用户 |
| POST | `/admin/tracks/batch` | 必须 | 批量导入歌曲 |
| POST | `/admin/interactions/batch` | 必须 | 批量导入交互 |

#### 训练与评测

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| POST | `/admin/training/preprocess` | 必须 | 启动数据预处理 |
| POST | `/admin/training/feature-engineering` | 必须 | 启动特征工程 |
| POST | `/admin/training/train-baseline` | 必须 | 训练 ItemCF + SVD |
| POST | `/admin/training/train-sasrec` | 必须 | 训练 SASRec |
| POST | `/admin/training/train-deepfm` | 必须 | 训练 DeepFM |
| POST | `/admin/training/train-all` | 必须 | 顺序执行完整训练流程 |
| POST | `/admin/training/evaluate` | 必须 | 启动模型评测 |
| GET | `/admin/training/progress/{task_id}/stream` | 必须 | SSE 实时进度流 |
| GET | `/admin/training/history` | 必须 | 获取训练历史列表 |
| GET | `/admin/training/progress` | 必须 | 获取所有进度（跳过 _report.json） |
| GET | `/admin/training/eval-progress` | 必须 | 获取评测进度列表 |
| GET | `/admin/training/eval-history` | 必须 | 获取评测历史列表 |
| GET | `/admin/training/eval-report/{task_id}` | 必须 | 获取特定评测报告 |

#### 模型版本管理

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/admin/training/model-versions` | 必须 | 获取所有模型版本信息 |
| GET | `/admin/training/model-versions/{model}` | 必须 | 获取特定模型的版本列表 |
| POST | `/admin/training/model-versions/{model}/{version_id}/promote` | 必须 | 手动提升指定版本 |

#### 调度器管理

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/admin/scheduler/jobs` | 必须 | 获取所有定时任务 |
| POST | `/admin/scheduler/schedule` | 必须 | 创建定时任务 |
| PUT | `/admin/scheduler/schedule/{schedule_id}` | 必须 | 更新定时任务 |
| DELETE | `/admin/scheduler/schedule/{schedule_id}` | 必须 | 删除定时任务 |
| PUT | `/admin/scheduler/threshold` | 必须 | 更新数据阈值配置 |
| GET | `/admin/scheduler/threshold-state` | 必须 | 获取阈值状态 |

### 4.2.5 管理前端路由 (`admin-web/src/router/`)

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | `Dashboard.vue` | 仪表盘：统计 + 最近训练 |
| `/data` | `DataImport.vue` | 数据导入管理 |
| `/training` | `Training.vue` | 训练控制 + SSE 实时日志 |
| `/scheduler` | `Scheduler.vue` | 定时任务管理 |
| `/models` | `Models.vue` | 模型状态 + 评测对比 + 版本历史 |
| `/login` | `Login.vue` | 管理员登录 |

---

## 4.3 核心算法/业务组件

### 4.3.1 JWT 双令牌鉴权 (`core/security.py` + `core/dependencies.py`)

**Token 结构**：

```
Access Token (有效期 15 分钟):
{
  "sub": "42",              // user_id 字符串
  "exp": 1712298600,        // 过期时间戳
  "type": "access"          // 类型标识
}

Refresh Token (有效期 7 天):
{
  "sub": "42",
  "exp": 1712892600,
  "type": "refresh"
}
```

**存储方式**：
- Access Token → 前端 `localStorage`，每次请求通过 `Authorization: Bearer <token>` Header 携带
- Refresh Token → 后端 `Set-Cookie` 写入浏览器，`HttpOnly`（JS 无法读取），`Path=/api/v1/auth`（仅认证接口可见），`SameSite=Lax`

**自动刷新流程** (`frontend/src/api/client.ts` 响应拦截器)：
```
API 返回 401
  → 检查 !originalRequest._retry 且 URL 不含 /auth/
  → _retry = true（防止无限循环）
  → auth.refreshToken() → POST /api/v1/auth/refresh
    → Cookie 自动携带 refresh_token
    → 后端 decode_token → 校验 type=="refresh" → 生成新 access_token 返回
  → 刷新成功 → 更新 localStorage → 用新 token 重发原始请求
  → 刷新失败 → auth.logout() → 清空状态 → 跳转 /login
```

**依赖注入三级认证** (`core/dependencies.py`)：

| 函数 | 用途 | 行为 |
|------|------|------|
| `get_current_user` | 强制认证 | 解析 Bearer Token → 查 DB 用户 → 返回 User 对象；失败抛 401 |
| `get_current_user_optional` | 可选认证 | 尝试解析 token，成功返回 User，失败返回 None；不抛异常 |
| `require_admin` | 管理员校验 | 依赖 get_current_user → 检查 `role == "admin"`；非 admin 抛 403 |

Token 解析优先从 `HTTPBearer` 提取，回退到 `Authorization` Header 手动解析。

### 4.3.2 推荐引擎核心 (`services/recommendation_service.py`)

`get_recommendations()` 函数是整个推荐系统的调度中枢，执行 4 级降级策略：

```
输入参数:
  db: AsyncSession    — 数据库会话
  user_id: int|None   — 用户ID（匿名为 None）
  size: int = 20      — 返回数量
  scene: str = "home_feed"  — 场景标识（预留多场景）
  current_track_id: str|None — 当前播放歌曲（预留相似推荐）

执行流程:
  [L1] if user_id:
         redis.get("rec:user:{user_id}")
         命中 → json.loads → 取 items[:size] → 直接返回
  [L2] if user_id:
         _ml_pipeline_recommend(db, user_id, size)
         → 调用 ml_pipeline.inference.pipeline.recommend()
         → 成功 → cache_recommendations() 写 Redis(TTL=30min) → 返回
         → 失败(ImportError/Exception) → 降级
  [L3] if user_id:
         SELECT * FROM offline_recommendations WHERE user_id=?
         → recommended_track_ids[:size] → _fetch_tracks_by_ids(db, ids) → 返回
  [L4] get_popular_tracks(db, limit=size)
         → SELECT * FROM tracks WHERE status=1 ORDER BY play_count DESC LIMIT ?
         → 返回
```

**`_ml_pipeline_recommend()` 内部细节**：

```
1. 动态导入: from ml_pipeline.inference.pipeline import recommend
   失败 → 返回 None（ML 管线不可用）

2. 获取用户序列: _get_user_sequence(user_id)
   → redis.lrange("user:seq:{user_id}", 0, 49)
   → 返回 ["DZ12345", "DZ67890", ...] 最近50首播放的歌曲ID
   → Redis 中无数据则返回空列表

3. 获取热门歌曲: get_popular_tracks(db, limit=50)
   → 从 MySQL 查询 play_count 最高的 50 首

4. 调用 ML 推理: ml_recommend(user_id, user_sequence, popular_tracks, top_k)
   → 返回 {"strategy": "sasrec_deepfm", "items": [{"track_id": "...", "score": 0.87}, ...]}

5. 用 DB 数据丰富: _fetch_tracks_by_ids(db, track_ids)
   → SELECT * FROM tracks WHERE track_id IN (...) AND status=1
   → 按 ML 返回顺序排列，补全 title/artist/cover_url 等

6. 附加 score 字段到每个 item
```

### 4.3.3 ML Pipeline 推理管线 (`ml_pipeline/inference/`)

#### `pipeline.py` — 推理总入口

```
recommend(user_id, user_sequence, popular_tracks, top_k=20, use_onnx=False)
  │
  ├── _models_available()
  │   检查 data/models/ 下 4 个子目录的 meta.json 是否存在
  │   返回 {"item_cf": bool, "svd": bool, "deepfm": bool, "sasrec": bool, "deepfm_onnx": bool}
  │
  ├── 策略选择:
  │   if 无任何模型 → "popularity_cold_start"
  │   if 无序列 && user_id==None → "cold_start_popular"
  │   if 有序列(>=3) && 有sasrec → "sasrec_deepfm" 或 "sasrec_only"
  │   if 有itemcf → "itemcf_deepfm" 或 "itemcf_only"
  │   else → "popularity_fallback"
  │
  ├── Step 1: multi_recall() 多路召回
  │   返回 list[(track_id, score, source)]，已去重合并
  │
  ├── Step 2: rank_candidates() 精排
  │   if 有deepfm && user_id != None → DeepFM 排序
  │   else → 直接用召回分数
  │
  └── Step 3: 格式化输出
      → {"strategy", "is_fallback", "items": [{"track_id", "score"}, ...], "debug": {...}}
```

#### `recall.py` — 多路召回

```
multi_recall(user_id, user_sequence, popular_tracks, itemcf_k=150, sasrec_k=150, popularity_k=50)
  │
  ├── SASRec 召回 (优先级最高):
  │   if user_sequence 长度 >= 3:
  │     sasrec_recall(user_sequence, top_k=150)
  │     → SASRecRecommender.recommend(seq, top_k)
  │     → 将序列 pad 到 MAX_SEQ_LEN → Transformer 前向传播 → 全量打分 → top_k
  │     → 结果写入 candidates[track_id] = (score, "sasrec")
  │
  ├── ItemCF 召回:
  │   if user_id != None:
  │     itemcf_recall(user_id, top_k=150)
  │     → ItemCF.recommend(user_id, top_k)
  │     → 查找用户历史交互物品 → 对每个物品找 top_k_similar 个相似物
  │     → 加权求和: score = Σ(similar(item, historic_item) * user_weight)
  │     → 排除已交互物品 → top_k
  │     → 如果 track_id 已在 candidates 中（来自 SASRec）:
  │         candidates[track_id] = (原分 + 新分*0.5, "sasrec+itemcf")  # 融合加分
  │       否则:
  │         candidates[track_id] = (score, "itemcf")
  │
  ├── Popularity 召回 (补充):
  │   popularity_recall(popular_tracks, top_k=50)
  │   → 分数 = 1/(排名+1) * 0.3（降权）
  │   → 仅添加 candidates 中不存在的 track_id
  │
  └── 按 score 降序排序 → 返回 list[(track_id, score, source)]
```

**模型懒加载**：`_get_item_cf()` 和 `_get_sasrec()` 使用全局变量 + 延迟实例化，首次调用时才从磁盘加载模型文件，后续调用直接复用。

#### `ranking.py` — DeepFM 精排

```
rank_candidates(user_id, candidate_track_ids, recall_scores, top_k=20, use_onnx=False)
  │
  ├── _load_features()
  │   从 Parquet 文件加载:
  │   - user_features.parquet → _user_features DataFrame
  │   - item_features.parquet → _item_features DataFrame
  │
  ├── _load_deepfm() 或 _load_onnx()
  │   从磁盘加载 DeepFM PyTorch 模型 或 ONNX Runtime Session
  │
  ├── 为每个候选 track 构建特征:
  │   for track_id in candidate_track_ids:
  │     查找 item_features 中该 track 的行
  │     sparse_vals = [user_idx, track_idx, age_bucket, gender, country_idx]  # 5维
  │     dense_vals  = [interaction_count, play_count, like_count, avg_completion, avg_rating,
  │                    danceability, energy, tempo, valence, acousticness,
  │                    log_popularity, item_interaction_count, item_avg_completion,
  │                    item_avg_rating, item_like_ratio]  # 15维
  │
  ├── 批量推理:
  │   if use_onnx:
  │     _onnx_session.run(None, {"sparse_inputs": array, "dense_inputs": array})
  │   else:
  │     _deepfm.predict(sparse_array, dense_array)  # PyTorch 推理
  │   → scores: ndarray of sigmoid probabilities
  │
  ├── 分数融合:
  │   for i, track_id:
  │     final_score = scores[i] * 0.7 + recall_scores[track_id] * 0.3
  │
  └── 按 final_score 降序排序 → 返回 top_k 个 (track_id, score)
```

### 4.3.4 DeepFM 模型架构 (`ml_pipeline/models/deepfm.py`)

```
输入:
  sparse_inputs: (batch, 5) — [user_idx, track_idx, age_bucket, gender, country_idx]
  dense_inputs:  (batch, 15) — 15 维连续特征

网络结构:
  ┌───────────────────────────────────────────────────────┐
  │                    DeepFM Model                       │
  │                                                       │
  │  sparse_inputs ──┬── First-Order (线性)               │
  │                  │   每个稀疏特征 Embedding(dim,1)     │
  │                  │   求和 → (batch, 1)                 │
  │                  │                                     │
  │                  ├── Second-Order (FM 二阶交叉)        │
  │                  │   每个稀疏特征 Embedding(dim, 64)   │
  │                  │   FM公式: 0.5*(Σ²-Σx²) → (batch,1) │
  │                  │                                     │
  │                  └── Deep (DNN)                        │
  │                      Embedding 拼接 dense → (batch,5*64+15)=335 │
  │                      Linear(335,256)→BN→ReLU→Dropout  │
  │                      Linear(256,128)→BN→ReLU→Dropout  │
  │                      Linear(128,64)→BN→ReLU→Dropout   │
  │                      Linear(64,1) → (batch, 1)         │
  │                                                       │
  │  logit = first_order + fm_output + dnn_output + bias  │
  │  output = sigmoid(logit) → (batch,)                   │
  └───────────────────────────────────────────────────────┘

训练: BCE Loss + Adam(lr=1e-3) + GradClip(5.0) + EarlyStopping(patience=5)
持久化: deepfm_model.pt (PyTorch) + deepfm_model.onnx (ONNX) + meta.json
```

### 4.3.5 SASRec 模型架构 (`ml_pipeline/models/sasrec.py`)

```
输入:
  input_seq: (batch, max_len=50) — padded item indices (0=padding)

网络结构:
  ┌───────────────────────────────────────────────────────┐
  │                    SASRec Model                       │
  │                                                       │
  │  input_seq → ItemEmbedding(num_items+1, 64)           │
  │            + PositionalEmbedding(50, 64)               │
  │            → Dropout → LayerNorm                      │
  │                                                       │
  │  ×2 Transformer Blocks:                               │
  │    ┌─────────────────────────────────────────────┐     │
  │    │ MultiheadAttention(hidden=64, heads=2)      │     │
  │    │   + Causal Mask (上三角, 防止看到未来)       │     │
  │    │ → Add + LayerNorm                           │     │
  │    │ → FeedForward(64→256→64, GELU, Dropout)     │     │
  │    │ → Add + LayerNorm                           │     │
  │    └─────────────────────────────────────────────┘     │
  │                                                       │
  │  取最后一个位置输出 → last_hidden: (batch, 64)         │
  │                                                       │
  │  预测:                                                │
  │    scores = last_hidden @ all_item_embeddings.T        │
  │    → (batch, num_items)                               │
  └───────────────────────────────────────────────────────┘

训练: BPR Loss (正样本 vs 负样本)
  loss = -log(sigmoid(pos_score - neg_score) + 1e-8)
  pos_score = dot(last_hidden, pos_item_emb)
  neg_score = dot(last_hidden, neg_item_emb)
  Adam(lr=1e-3) + GradClip(5.0) + EarlyStopping(patience=8)

推理: recommend(seq, top_k=20)
  pad 序列 → 前向传播 → 取全量打分 → 排除已见 → top_k
```

### 4.3.6 ItemCF 模型 (`ml_pipeline/models/item_cf.py`)

```
训练:
  1. 构建 user-item 稀疏矩阵 (scipy.sparse.csr_matrix)
     - 行=用户，列=物品
     - 值=completion_rate（正交互的播放完成度，隐式反馈权重）
  2. 转置得到 item-user 矩阵
  3. 计算 item 间余弦相似度: cosine_similarity(item_matrix) → (num_items, num_items) 方阵
  4. 对角线置零（排除自身相似）

推理: recommend(user_id, top_k=20)
  1. 获取用户历史交互向量: user_items = user_item_matrix[user_idx].toarray()
  2. 对每个交互过的物品 i: scores += item_sim_matrix[i] * user_items[i]
  3. 排除已交互物品 (scores[interacted] = -inf)
  4. argsort → top_k → 转换 track_idx 为 track_id

持久化: item_sim_matrix.npy + user_item_matrix.npz + meta.json
加载时还需: user2idx.parquet + track2idx.parquet（ID映射）
```

### 4.3.7 音频代理机制 (`api/tracks.py` → `proxy_preview()`)

```
前端请求: GET /api/v1/tracks/DZ12345/preview
  │
  ▼
1. 查 DB: get_track_by_id(db, "DZ12345") → Track 对象
   - 无此歌 → 404
   - 无 preview_url → 404 "No preview available"

2. 提取 Deezer 数字 ID: "DZ12345" → "12345"

3. 调用 Deezer API 获取最新签名 URL:
   GET https://api.deezer.com/track/12345
   → 解析 JSON → 取 preview 字段（含 hdnea 时效性签名）
   失败则回退到 DB 中存储的 preview_url

4. 流式代理:
   httpx.AsyncClient.stream("GET", stream_url, headers=_PROXY_HEADERS)
   - User-Agent 伪装浏览器
   - Referer: https://www.deezer.com/
   - 8192 bytes 分块回传
   - Content-Type: audio/mpeg
   - Cache-Control: no-store（签名有时效性，不可缓存）
```

### 4.3.8 交互记录双写机制 (`services/interaction_service.py`)

```
log_interaction(db, user_id, track_id, interaction_type, rating, play_duration)
  │
  ├── 1. 计算 completion_rate:
  │     if play_duration != None && interaction_type == 1 (play):
  │       查 DB 获取 track.duration_ms
  │       completion_rate = min(play_duration / duration_ms, 1.0)
  │
  ├── 2. 写入 MySQL:
  │     INSERT INTO user_interactions
  │       (user_id, track_id, interaction_type, rating, play_duration, completion_rate)
  │     await db.flush()  // 等待写入完成
  │
  ├── 3. 更新歌曲播放计数:
  │     if interaction_type == 1 (play):
  │       UPDATE tracks SET play_count = play_count + 1 WHERE track_id = ?
  │
  └── 4. 更新 Redis 滑动窗口:
        if interaction_type in (1, 2):  // play 或 like
          redis.lpush("user:seq:{user_id}", track_id)  // 左端插入最新
          redis.ltrim("user:seq:{user_id}", 0, 49)     // 保留最近50首
          redis.expire("user:seq:{user_id}", 86400*7)   // TTL 7天
        // 这个序列是 SASRec 模型在线推理的输入
```

### 4.3.9 前端播放器状态机 (`stores/player.ts`)

```
状态:
  currentTrack: Track | null   — 当前播放曲目
  playlist: Track[]            — 播放列表
  currentIndex: number         — 当前曲目在列表中的索引
  isPlaying: boolean           — 是否正在播放
  currentTime: number          — 当前播放秒数
  duration: number             — 总时长秒数
  volume: number               — 音量 0-1
  audio: HTMLAudioElement      — 底层 Audio 元素（懒初始化）

生命周期:
  play(track, tracks?) → 初始化 Audio → 设置 src → play()
    - src = /api/v1/tracks/{track_id}/preview（走后端代理）
    - 无 preview_url → simulatePlayback()（定时器模拟进度）

  Audio 事件监听:
    timeupdate → 更新 currentTime
    loadedmetadata → 更新 duration（流媒体可能无 Content-Length，回退到 track.metadata）
    ended → logPlayInteraction() → next()（记录交互并播放下一首）
    error → isPlaying = false

  logPlayInteraction():
    playDurationMs = currentTime * 1000
    if < 1000ms → 忽略（太短不记录）
    POST /api/v1/interactions {track_id, interaction_type:1, play_duration}
    失败 → navigator.sendBeacon() 降级

  页面卸载 (beforeunload):
    if 正在播放 → sendBeacon 发送交互记录（保证数据不丢失）

  持久化:
    localStorage('player_last_track') → 刷新页面恢复上次播放曲目
    localStorage('player_volume') → 刷新页面恢复音量
```

### 4.3.10 收藏乐观更新 (`stores/favorites.ts`)

```
toggleFavorite(trackId):
  1. 读取 wasFavorited = favoriteIds.has(trackId)
  2. 乐观更新:
     if wasFavorited → favoriteIds.delete(trackId)  // 立即从 Set 删除
     else → favoriteIds.add(trackId)                 // 立即添加到 Set
  3. 发送 API:
     if wasFavorited → DELETE /api/v1/favorites/{trackId}
     else → POST /api/v1/favorites/{trackId}
  4. 失败回滚:
     if API 失败 → 恢复 favoriteIds 到更新前状态
  // UI 立即响应，不等 API 返回
```
