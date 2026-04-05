# 6. 复现与部署指南 (Reproduction Guide)

## 6.1 从零部署（Docker Compose 一键启动）

以下是从 `git clone` 到系统完整运行的全部操作步骤：

### 前置条件

确保宿主机已安装：
- Docker >= 20.0
- Docker Compose >= 2.0
- Git

### 步骤 1：克隆代码

```bash
git clone <repository-url> music_rec
cd music_rec
```

### 步骤 2：创建环境变量文件

```bash
cp .env.example .env
```

`.env` 文件内容已预置好，无需修改即可直接使用。关键配置项说明：

| 配置项 | 默认值 | 是否需要修改 |
|--------|--------|-------------|
| `MYSQL_ROOT_PASSWORD` | `music_rec_root_2026` | 生产环境必须改 |
| `MYSQL_PASSWORD` | `music_app_pass_2026` | 生产环境必须改 |
| `REDIS_PASSWORD` | `redis_music_2026` | 生产环境必须改 |
| `JWT_SECRET_KEY` | `super-secret-key-change-in-production-2026` | **生产环境必须改** |
| `BACKEND_PORT` / 映射 | 18000 | 不冲突可不改 |

### 步骤 3：启动全部服务

```bash
docker compose up -d --build
```

此命令按依赖顺序启动 5 个容器：

```
启动顺序：
  musicrec_mysql   ──── healthcheck 通过 ────┐
  musicrec_redis   ──── healthcheck 通过 ────┤
                                               ├──► musicrec_backend 启动
                                               ├──► musicrec_seeder 执行后退出
                                               └──► musicrec_frontend 启动
```

首次启动约需 3-5 分钟（构建镜像 + 种子数据 + Deezer API 网络请求）。

### 步骤 4：验证服务状态

```bash
# 检查所有容器状态
docker compose ps

# 期望输出（seeder 已退出，其余 running）：
# musicrec_mysql     running (healthy)    0.0.0.0:13307->3306/tcp
# musicrec_redis     running (healthy)    0.0.0.0:16379->6379/tcp
# musicrec_backend   running              0.0.0.0:18000->8000/tcp
# musicrec_frontend  running              0.0.0.0:13000->3000/tcp
# musicrec_seeder    exited (0)

# 检查后端健康
curl http://localhost:18000/health
# 期望: {"status":"healthy","service":"MusicRec"}

# 检查数据库是否已初始化
docker exec musicrec_mysql mysql -umusic_app -pmusic_app_pass_2026 music_rec -e "SELECT COUNT(*) FROM tracks;"
# 期望: 显示歌曲数量（约200首）
```

### 步骤 5：访问系统

| 服务 | URL |
|------|-----|
| **前端界面** | http://localhost:13000 |
| **后端 API 文档** | http://localhost:18000/docs |
| **后端 ReDoc 文档** | http://localhost:18000/redoc |

**默认管理员账号**：`admin` / `admin123`

### 步骤 6：（可选）训练 ML 模型

系统在无模型状态下可正常运行（降级到热门推荐）。如需启用个性化推荐，需训练模型：

```bash
# 进入后端容器
docker exec -it musicrec_backend bash

# Step 1: 数据预处理（从 MySQL 读取 → 清洗 → 切分 → 存为 Parquet）
python -m ml_pipeline.data_process.preprocess

# Step 2: 特征工程（构建用户/物品特征 → 负采样 → DeepFM 数据集）
python -m ml_pipeline.data_process.feature_engineering

# Step 3: 训练基线模型（ItemCF + SVD）
python -m ml_pipeline.training.train_baseline

# Step 4: 训练 DeepFM 排序模型
python -m ml_pipeline.training.train_deepfm

# Step 5: 训练 SASRec 序列模型
python -m ml_pipeline.training.train_sasrec

# 退出容器
exit
```

训练完成后，模型文件保存在 `data/models/` 下。后端下次推荐请求时会自动加载。

---

## 6.2 本地开发模式（不使用 Docker）

适用于需要频繁修改代码的开发场景。

### 后端本地运行

```bash
# 前置：Python >= 3.11，uv 包管理器

# 1. 安装依赖
uv sync

# 2. 仅启动 MySQL 和 Redis（仍用 Docker）
docker compose up -d musicrec_mysql musicrec_redis

# 3. 创建 .env.local 覆盖 Docker 内部地址
cat > .env.local << 'EOF'
MYSQL_HOST=localhost
MYSQL_PORT=13307
REDIS_HOST=localhost
REDIS_PORT=16379
EOF

# 4. 运行种子数据（首次）
uv run python scripts/seed_data.py
uv run python ml_pipeline/data_process/generate_synthetic_data.py

# 5. 启动后端
uv run uvicorn app.main:app --host 0.0.0.0 --port 18000 --reload
```

### 前端本地运行

```bash
# 前置：Node.js >= 20

cd frontend

# 1. 安装依赖
npm install

# 2. 启动开发服务器（自动代理 /api → localhost:18000）
npm run dev
```

### 训练模型（本地）

```bash
# 确保后端可用，MySQL 有数据
uv run python -m ml_pipeline.data_process.preprocess
uv run python -m ml_pipeline.data_process.feature_engineering
uv run python -m ml_pipeline.training.train_baseline
uv run python -m ml_pipeline.training.train_deepfm
uv run python -m ml_pipeline.training.train_sasrec
```

---

## 6.3 常用运维命令

```bash
# 查看后端日志
docker compose logs -f musicrec_backend

# 查看前端日志
docker compose logs -f musicrec_frontend

# 重新构建并启动（代码变更后）
docker compose up -d --build musicrec_backend

# 仅重启种子数据（清空后重新导入）
docker compose run --rm musicrec_seeder

# 停止全部服务
docker compose down

# 停止并删除数据卷（完全重置）
docker compose down -v

# 进入 MySQL 命令行
docker exec -it musicrec_mysql mysql -umusic_app -pmusic_app_pass_2026 music_rec

# 连接 Redis
docker exec -it musicrec_redis redis-cli -a redis_music_2026

# 查看 Redis 中的推荐缓存
docker exec -it musicrec_redis redis-cli -a redis_music_2026 KEYS "rec:*"

# 查看用户播放序列
docker exec -it musicrec_redis redis-cli -a redis_music_2026 LRANGE "user:seq:1" 0 -1
```

---

## 6.4 高频踩坑点及解决方案

### 踩坑 1：Windows 上 `aiomysql` 报 `RuntimeError: Event loop is closed`

**现象**：在 Windows 上直接运行 `preprocess.py` 或 `generate_synthetic_data.py` 时崩溃。

**原因**：Windows 的默认事件循环策略（ProactorEventLoop）与 aiomysql 不兼容。

**解决**：这些脚本已在入口处添加了兼容代码：
```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
如果自行编写新的异步脚本，也必须添加此代码。

---

### 踩坑 2：Deezer API 种子数据抓取超时或失败

**现象**：`seed_data.py` 运行时打印 `⚠ Deezer API error` 或卡住。

**原因**：Deezer API 在国内可能被限速或不稳定。

**解决**：
- 方案 A：配置代理后重试 `HTTP_PROXY=http://proxy:port docker compose run --rm musicrec_seeder`
- 方案 B：手动修改 `scripts/seed_data.py` 中 `fetch_tracks_from_deezer()` 的 `timeout` 参数增大到 30
- 方案 C：跳过 Deezer 数据，使用纯合成数据，修改 `seed_data.py` 直接 INSERT 合成歌曲（不依赖外部 API）

---

### 踩坑 3：端口被占用

**现象**：`docker compose up` 报 `port is already allocated`。

**原因**：本地已有服务占用 13307、16379、18000 或 13000 端口。

**解决**：
```bash
# 查找占用进程
# Windows
netstat -ano | findstr :13307
# Linux/Mac
lsof -i :13307

# 方案 A：结束占用进程
kill -9 <PID>

# 方案 B：修改 .env 中的端口映射
MYSQL_PORT=23307   # 改为其他未占用端口
# 同时修改 .env.local（如有）中的对应端口
```

---

### 踩坑 4：MySQL 容器启动后立刻退出

**现象**：`docker compose ps` 显示 MySQL 容器 `restarting` 或 `unhealthy`。

**原因**：通常是由于数据卷损坏或之前的容器非正常退出。

**解决**：
```bash
# 完全清除数据卷后重启
docker compose down -v
docker compose up -d musicrec_mysql
# 等待 30 秒确认 healthy
docker compose ps
```

---

### 踩坑 5：前端页面打开空白或 API 报 404

**现象**：浏览器打开 `http://localhost:13000` 白屏，或控制台报 `/api/v1/...` 404。

**原因**：Vite 开发服务器的代理配置中 `VITE_API_PROXY_TARGET` 未正确指向后端。

**解决**：
```bash
# Docker 环境：确认 frontend 容器的环境变量
docker exec musicrec_frontend env | grep VITE
# 期望: VITE_API_PROXY_TARGET=http://musicrec_backend:8000

# 本地开发：确认 vite.config.ts 中的 target
# 默认: http://localhost:18000
# 如果后端不在 18000，需修改或设置环境变量:
export VITE_API_PROXY_TARGET=http://localhost:你的端口
npm run dev
```

---

### 踩坑 6：ML 模型训练报 `No module named 'ml_pipeline'`

**现象**：在宿主机直接运行 `python -m ml_pipeline.training.train_baseline` 报 ModuleNotFoundError。

**原因**：宿主机 Python 环境未正确设置 `PYTHONPATH`。

**解决**：
```bash
# 方案 A：使用 uv 运行（自动处理路径）
uv run python -m ml_pipeline.training.train_baseline

# 方案 B：手动设置 PYTHONPATH
PYTHONPATH=/path/to/music_rec python -m ml_pipeline.training.train_baseline

# 方案 C：在 Docker 容器内运行
docker exec -it musicrec_backend python -m ml_pipeline.training.train_baseline
```

---

### 踩坑 7：ML 模型训练报 `No interactions found`

**现象**：`preprocess.py` 打印 `No interactions found! Run generate_synthetic_data.py first.`

**原因**：数据库中还没有用户交互数据。

**解决**：
```bash
# 必须按顺序执行：
# 1. 先运行种子数据（创建歌曲）
uv run python scripts/seed_data.py
# 2. 再生成合成用户和交互
uv run python ml_pipeline/data_process/generate_synthetic_data.py
# 3. 最后运行预处理
uv run python -m ml_pipeline.data_process.preprocess
```

---

### 踩坑 8：Redis 连接被拒绝

**现象**：后端日志打印 `Redis cache read failed: Error 111 Connection refused`。

**原因**：Redis 容器未启动或后端配置的 Redis 地址不正确。

**解决**：
```bash
# 检查 Redis 容器状态
docker compose ps musicrec_redis
# 如果不是 running/healthy，重启：
docker compose restart musicrec_redis

# Docker 环境：后端 REDIS_HOST 应为 musicrec_redis（容器名）
# 本地开发：REDIS_HOST 应为 localhost，REDIS_PORT 为 16379
```

---

### 踩坑 9：前端登录后刷新页面丢失状态

**现象**：登录成功后刷新页面，变成未登录状态。

**原因**：`localStorage` 被浏览器隐私模式或安全策略阻止。

**解决**：
- 不要在浏览器无痕/隐私模式下使用
- 检查浏览器控制台是否有 `localStorage.setItem` 报错
- 检查浏览器设置是否阻止了第三方 Cookie/存储

---

### 踩坑 10：音频无法播放

**现象**：点击歌曲播放按钮后无声音，控制台报 404 或 CORS 错误。

**原因**：
- Deezer CDN 的签名 URL 有时效性（存储在 DB 中的 URL 可能已过期）
- 部分歌曲在 Deezer 上无 preview 音频

**解决**：
- 后端已实现自动刷新签名 URL 机制（`proxy_preview()` 每次调用 Deezer API 获取最新 URL）
- 如果 Deezer API 也返回 null preview，则该歌曲确实无试听音频
- 检查后端日志中 `CDN returned 403/404` 的警告，可能是 IP 被限流，等待后重试

---

## 6.5 系统重启与数据持久化

```
数据持久化机制:
┌──────────────────────────────────────────────────────────┐
│ Docker Named Volumes:                                     │
│   musicrec_mysql_data  → MySQL 数据文件（用户、歌曲、交互）│
│   musicrec_redis_data  → Redis RDB/AOF（缓存数据，可丢失） │
│                                                           │
│ Host 挂载（Bind Mounts）:                                  │
│   ./app/      → 后端代码（热重载）                         │
│   ./ml_pipeline/ → ML 管线代码（热重载）                   │
│   ./data/     → 模型文件和 Parquet 数据（持久化）           │
│   ./frontend/src/ → 前端源码（热重载）                     │
└──────────────────────────────────────────────────────────┘

重启策略:
  docker compose restart           # 重启服务，保留数据
  docker compose down && up -d     # 重建容器，保留数据卷
  docker compose down -v           # ⚠️ 删除数据卷，完全重置
```

**正常重启**（`docker compose restart` 或服务器重启）：
- MySQL 数据保留（命名卷）
- Redis 缓存清空（可接受，下次请求自动重建）
- ML 模型文件保留（`data/models/` 在宿主机上）
- 用户状态保留（MySQL + localStorage）

**完全重置**（`docker compose down -v`）：
- 删除所有数据卷
- 需要重新执行种子数据 (`musicrec_seeder`)
- 需要重新训练 ML 模型
