# 5. 存储与状态流转 (Storage & State Management)

## 5.1 数据库/持久化设计

### 5.1.1 MySQL 表结构全景

系统共 9 张核心表，全部使用 InnoDB 引擎、utf8mb4 字符集：

```
┌──────────────┐       ┌──────────────┐       ┌────────────────────┐
│    users      │       │    tracks    │       │  user_interactions │
│──────────────│       │──────────────│       │────────────────────│
│ user_id (PK) │◄──┐   │ track_id(PK) │◄──┐   │ interaction_id(PK) │
│ username     │   │   │ title        │   │   │ user_id (FK→users) │
│ password_hash│   │   │ artist_name  │   │   │ track_id(FK→tracks)│
│ role         │   │   │ album_name   │   │   │ interaction_type   │
│ age          │   │   │ release_year │   │   │ rating             │
│ gender       │   │   │ duration_ms  │   │   │ play_duration      │
│ country      │   │   │ play_count   │   │   │ completion_rate    │
│ created_at   │   │   │ status       │   │   │ created_at         │
│ last_login   │   │   │ preview_url  │   │   └────────────────────┘
└──────────────┘   │   │ cover_url    │   │            │
      │            │   │ created_at   │   │            │
      │            │   └──────────────┘   │            │
      │            │         │             │            │
      │            │         │             │            │
      │    ┌───────┴───┐    │    ┌────────┴────────────┐
      │    │user_favorites│  │    │offline_recommendations│
      │    │─────────────│    │    │─────────────────────│
      │    │user_id(PK,FK)│   │    │ user_id (PK, FK)    │
      │    │track_id(PK,FK)│───┘    │ recommended_ids(JSON)│
      │    │created_at   │         │ updated_at          │
      │    └─────────────┘         └─────────────────────┘
      │
      │     ┌──────────────┐     ┌──────────────┐
      │     │track_features│     │     tags      │
      │     │──────────────│     │──────────────│
      │     │ track_id(PK) │     │ tag_id (PK)  │
      │     │ danceability │     │ tag_name     │
      │     │ energy       │     └──────┬───────┘
      │     │ tempo        │            │
      │     │ valence      │     ┌──────┴───────┐
      │     │ acousticness │     │  track_tags   │
      │     │ updated_at   │     │──────────────│
      │     └──────────────┘     │ track_id(PK) │
      │            ▲             │ tag_id (PK)  │
      └────────────┼─────────────┘──────────────┘
                   └───────────── FK ────────────┘
```

### 5.1.2 各表字段详解

#### `users` — 用户表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `user_id` | INT | PK, AUTO_INCREMENT | 用户唯一标识 |
| `username` | VARCHAR(50) | NOT NULL, UNIQUE | 登录用户名，不可重复 |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt 哈希后的密码，原文不存储 |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT 'user' | 角色：`user` 或 `admin` |
| `age` | INT | NULL | 年龄，注册时可选填 |
| `gender` | TINYINT | NULL | 性别：0=未知，1=男，2=女 |
| `country` | VARCHAR(50) | NULL | 国家/地区 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 注册时间 |
| `last_login` | TIMESTAMP | NULL | 最后登录时间，每次 login 时更新 |

#### `tracks` — 歌曲表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `track_id` | VARCHAR(64) | PK | 歌曲唯一标识，格式 `DZ{deezer_numeric_id}`（如 `DZ3135556`） |
| `title` | VARCHAR(255) | NOT NULL | 歌曲标题 |
| `artist_name` | VARCHAR(255) | NULL | 歌手/艺术家名 |
| `album_name` | VARCHAR(255) | NULL | 专辑名 |
| `release_year` | INT | NULL | 发行年份 |
| `duration_ms` | INT | NULL | 时长（毫秒），从 Deezer API 获取 |
| `play_count` | INT | NOT NULL, DEFAULT 0 | 累计播放次数，每次 play 交互 +1 |
| `status` | TINYINT | NOT NULL, DEFAULT 1 | 状态：1=正常，0=已下架 |
| `preview_url` | VARCHAR(512) | NULL | 试听音频 URL（Deezer CDN，含时效签名） |
| `cover_url` | VARCHAR(512) | NULL | 封面图 URL |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 入库时间 |

**索引**：
- `idx_status(status)` — 按状态过滤
- `idx_play_count(play_count DESC)` — 热门排行排序

#### `user_interactions` — 用户行为日志表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `interaction_id` | BIGINT | PK, AUTO_INCREMENT | 交互记录唯一标识 |
| `user_id` | INT | NOT NULL, FK→users | 行为发起用户 |
| `track_id` | VARCHAR(64) | NOT NULL, FK→tracks | 目标歌曲 |
| `interaction_type` | TINYINT | NOT NULL | 行为类型：1=play，2=like，3=skip，4=rate |
| `rating` | FLOAT | NULL | 评分（仅 interaction_type=4 时有值，范围 0-5） |
| `play_duration` | INT | NULL | 实际播放时长（毫秒），前端上报 |
| `completion_rate` | FLOAT | NULL | 播放完成度 = play_duration / duration_ms，范围 0-1 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 行为发生时间 |

**索引**：
- `idx_user_time(user_id, created_at)` — 按用户查历史
- `idx_track_time(track_id, created_at)` — 按歌曲查趋势
- `idx_type(interaction_type)` — 按类型统计

**外键**：`user_id → users(user_id) ON DELETE CASCADE`，`track_id → tracks(track_id) ON DELETE CASCADE`

#### `track_features` — 歌曲多模态特征表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `track_id` | VARCHAR(64) | PK, FK→tracks | 歌曲标识 |
| `danceability` | FLOAT | NULL | 舞蹈性（0-1），值越高越适合跳舞 |
| `energy` | FLOAT | NULL | 能量（0-1），值越高越激烈 |
| `tempo` | FLOAT | NULL | 节拍速度（BPM，60-200） |
| `valence` | FLOAT | NULL | 情感正负（0-1），值越高越积极欢快 |
| `acousticness` | FLOAT | NULL | 原声性（0-1），值越高越不插电 |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE | 最后更新时间 |

**数据来源**：种子数据阶段由 `seed_data.py` 随机生成（`random.uniform`），生产环境应从 Spotify Audio Features API 或音频分析工具提取真实值。

#### `tags` — 标签表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `tag_id` | INT | PK, AUTO_INCREMENT | 标签唯一标识 |
| `tag_name` | VARCHAR(100) | NOT NULL, UNIQUE | 标签名，如 Pop、Rock、Hip-Hop |

#### `track_tags` — 歌曲-标签关联表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `track_id` | VARCHAR(64) | PK, FK→tracks | 歌曲标识 |
| `tag_id` | INT | PK, FK→tags | 标签标识 |

多对多关系：一首歌可以有多个标签（流派），一个标签对应多首歌。

#### `user_favorites` — 用户收藏表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `user_id` | INT | PK, FK→users | 用户标识 |
| `track_id` | VARCHAR(64) | PK, FK→tracks | 歌曲标识 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 收藏时间 |

联合主键 `(user_id, track_id)`，同一用户不可重复收藏同一首歌。

#### `offline_recommendations` — 离线推荐兜底表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `user_id` | INT | PK, FK→users | 用户标识 |
| `recommended_track_ids` | JSON | NOT NULL | 预计算的推荐歌曲 ID 列表，如 `["DZ123","DZ456",...]` |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE | 推荐生成时间 |

#### `artists` — 歌手表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `artist_id` | INT | PK, AUTO_INCREMENT | 歌手唯一标识 |
| `name` | VARCHAR(255) | NOT NULL | 歌手/艺术家名 |
| `deezer_id` | INT | NULL | Deezer 歌手 ID |
| `image_url` | VARCHAR(512) | NULL | 歌手图片 URL |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |

#### `artist_favorites` — 歌手收藏表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `user_id` | INT | PK, FK→users | 用户标识 |
| `artist_id` | INT | PK, FK→artists | 歌手标识 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 收藏时间 |

#### `training_schedules` — 训练调度表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schedule_id` | INT | PK, AUTO_INCREMENT | 调度 ID |
| `name` | VARCHAR(100) | NOT NULL | 任务名称 |
| `task_type` | VARCHAR(50) | NOT NULL | 任务类型（train_all/evaluate） |
| `trigger_type` | VARCHAR(20) | NOT NULL | 触发类型（cron/interval/threshold） |
| `trigger_args` | JSON | NOT NULL | 触发参数 |
| `enabled` | BOOLEAN | NOT NULL, DEFAULT TRUE | 是否启用 |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**trigger_args 示例**：
- Cron: `{"cron": "0 2 * * *"}`
- Interval: `{"minutes": 60}`
- Threshold: `{"interaction_delta": 100}`

#### `training_threshold_state` — 训练阈值状态表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | 主键 |
| `last_interaction_count` | INT | NOT NULL, DEFAULT 0 | 上次训练时交互数 |
| `last_check_time` | TIMESTAMP | NULL | 上次检查时间 |

---

### 5.1.3 ML Pipeline 数据存储（Parquet 文件）

训练流程在 `data/processed/` 目录生成以下 Parquet 文件：

| 文件名 | 内容 | 行数 | 列 |
|--------|------|------|-----|
| `all_interactions.parquet` | 清洗后的全部交互 | ~数千-数万 | interaction_id, user_id, track_id, interaction_type, rating, play_duration, completion_rate, label, user_idx, track_idx, created_at |
| `train.parquet` | 训练集（时序切分前90%） | 同上×0.8 | 同上 |
| `val.parquet` | 验证集 | 同上×0.1 | 同上 |
| `test.parquet` | 测试集 | 同上×0.1 | 同上 |
| `tracks.parquet` | 歌曲信息+声学特征 | ~200+ | track_id, title, artist_name, duration_ms, play_count, danceability, energy, tempo, valence, acousticness |
| `users.parquet` | 用户信息 | ~60+ | user_id, username, age, gender, country, created_at |
| `user2idx.parquet` | user_id → 连续整数索引映射 | 同用户数 | user_id, user_idx |
| `track2idx.parquet` | track_id → 连续整数索引映射 | 同歌曲数 | track_id, track_idx |
| `user_features.parquet` | 用户特征向量 | 同用户数 | user_id, age_bucket, gender, country_idx, interaction_count, play_count, like_count, avg_completion, avg_rating |
| `item_features.parquet` | 物品特征向量 | 同歌曲数 | track_id, danceability, energy, tempo, valence, acousticness, log_popularity, item_interaction_count, item_avg_completion, item_avg_rating, item_like_ratio |
| `train_deepfm.parquet` | DeepFM 训练集（含负采样） | 正样本×(1+4) | user_idx, track_idx, label, ... + 全部用户/物品特征列 |
| `val_deepfm.parquet` | DeepFM 验证集 | 同 val | 同上 |
| `test_deepfm.parquet` | DeepFM 测试集 | 同 test | 同上 |
| `user_sequences.json` | 用户播放序列 | 同活跃用户数 | `{"user_id_str": ["track_id1", "track_id2", ...], ...}` |
| `feature_meta.json` | 特征元数据 | 1 | sparse_features, dense_features, sparse_dims, num_users, num_items |

### 5.1.4 训练好的模型文件

#### 生产模型目录 (`data/models/`)

推理代码**始终**从此目录加载模型：

| 目录 | 文件 | 说明 |
|------|------|------|
| `data/models/item_cf/` | `item_sim_matrix.npy` | item-item 余弦相似度矩阵 (num_items × num_items) |
| | `user_item_matrix.npz` | 稀疏 user-item 交互矩阵 (scipy sparse 格式) |
| | `user2idx.parquet` | 用户 ID 映射 |
| | `track2idx.parquet` | 歌曲 ID 映射 |
| | `meta.json` | 模型元数据 |
| `data/models/svd/` | `svd_model.pt` | PyTorch state_dict（user/item Embedding + bias） |
| | `item_embeddings.npy` | 全量 item embedding 向量 |
| | `user_embeddings.npy` | 全量 user embedding 向量 |
| | `meta.json` | 模型元数据 |
| `data/models/deepfm/` | `deepfm_model.pt` | PyTorch state_dict（全部权重） |
| | `deepfm_model.onnx` | ONNX 导出版本（可选） |
| | `meta.json` | `{"sparse_features": [...], "dense_features": [...], "sparse_dims": {...}}` |
| `data/models/sasrec/` | `sasrec_model.pt` | PyTorch state_dict（Transformer 权重） |
| | `meta.json` | `{"num_items": M, "hidden_dim": 64, "num_heads": 2, ...}` |

#### 版本化模型目录 (`data/model_versions/`)

每次训练保存版本化副本：

```
data/model_versions/
├── item_cf/
│   ├── 20250421_123456/              # 版本 ID（时间戳）
│   │   ├── item_sim_matrix.npy
│   │   ├── user_item_matrix.npz
│   │   ├── user2idx.parquet
│   │   ├── track2idx.parquet
│   │   └── meta.json
│   ├── 20250420_100000/
│   └── ...
├── svd/
├── deepfm/
└── sasrec/
```

#### 模型注册表

`data/model_registry.json` — 模型版本注册表，记录所有版本的元数据、指标和状态。

详见：[8. 模型版本管理系统](./08_model_versioning.md)

#### 进度文件目录

```
data/training_progress/                # 训练进度文件
├── {task_id}.json                     # 任务进度（原子写）

data/evaluation_progress/              # 评测进度文件
├── {task_id}.json                     # 评测进度
└── {task_id}_report.json              # 评测结果报告
```
| `data/models/deepfm/` | `deepfm_model.pt` | PyTorch state_dict（全部权重） |
| | `deepfm_model.onnx` | ONNX 导出版本（可选，用于高性能推理） |
| | `meta.json` | `{"sparse_features": [...], "dense_features": [...], "sparse_dims": {...}}` |
| `data/models/sasrec/` | `sasrec_model.pt` | PyTorch state_dict（Transformer 权重） |
| | `meta.json` | `{"num_items": M, "hidden_dim": 64, "num_heads": 2, "num_blocks": 2, "max_len": 50}` |

---

## 5.2 Redis 数据结构

Redis 使用数据库 0，存储两类数据：

### 5.2.1 推荐结果缓存

| Key 模式 | 数据类型 | TTL | 写入时机 | 读取时机 |
|----------|---------|-----|---------|---------|
| `rec:user:{user_id}` | String (JSON) | 1800 秒 (30 分钟) | ML Pipeline 推理成功后写入 | `get_recommendations()` L1 策略 |

**JSON 结构**：
```json
{
  "strategy": "sasrec_deepfm",
  "items": [
    {"track_id": "DZ123", "title": "...", "artist_name": "...", "score": 0.87},
    ...
  ]
}
```

### 5.2.2 用户播放序列（SASRec 输入）

| Key 模式 | 数据类型 | TTL | 写入时机 | 读取时机 |
|----------|---------|-----|---------|---------|
| `user:seq:{user_id}` | List | 604800 秒 (7 天) | 每次 play/like 交互 `LPUSH` | `_get_user_sequence()` → `LRANGE 0 49` |

**操作序列**：
```
# 写入（每次 play 或 like 交互触发）
LPUSH user:seq:42 "DZ98765"          # 左端插入最新的 track_id
LTRIM user:seq:42 0 49                # 截断保留最近 50 首
EXPIRE user:seq:42 604800             # 重置 TTL 7 天

# 读取（推荐请求时获取用户序列）
LRANGE user:seq:42 0 49               # 返回 ["DZ98765", "DZ54321", ..., "DZ111"]
                                       # 索引 0 是最新的，索引 49 是最旧的
```

**数据流向**：
```
前端播放结束
  → POST /api/v1/interactions {interaction_type: 1}
    → interaction_service.log_interaction()
      → MySQL INSERT user_interactions      // 持久化
      → Redis LPUSH user:seq:{user_id}      // 实时更新序列
    → 下次推荐请求
      → _get_user_sequence() 从 Redis LRANGE 读取
      → 传入 SASRec 模型推理
```

---

## 5.3 全局状态管理

### 5.3.1 后端状态

后端为无状态设计，所有持久化状态存储在外部（MySQL/Redis），但有以下运行时单例：

| 单例 | 位置 | 初始化时机 | 生命周期 |
|------|------|-----------|---------|
| `Settings` | `config.py` → `get_settings()` `@lru_cache` | 首次调用 | 进程生命周期 |
| `AsyncEngine` | `database.py` → `engine` | 模块加载时 | 进程生命周期 |
| `async_session_factory` | `database.py` | 模块加载时 | 进程生命周期 |
| `redis_client` | `utils/__init__.py` → `get_redis()` | 首次调用 | 进程生命周期，`close_redis()` 在 shutdown 时调用 |
| ML 模型实例 | `inference/recall.py` 和 `ranking.py` 的全局变量 | 首次推荐请求时懒加载 | 进程生命周期 |

### 5.3.2 前端状态（Pinia Stores）

#### `auth` Store (`stores/auth.ts`)

| 状态字段 | 类型 | 来源 | 持久化 |
|----------|------|------|--------|
| `accessToken` | `string \| null` | login/register API 响应 | `localStorage('access_token')` |
| `user` | `User \| null` | login/register API 响应 | `localStorage('user_info')` JSON |

**计算属性**：
- `isLoggedIn` → `!!accessToken`
- `isAdmin` → `user?.role === 'admin'`

**状态流转**：
```
应用启动:
  accessToken = localStorage.getItem('access_token')
  user = JSON.parse(localStorage.getItem('user_info'))

登录成功:
  setAuth(token, userInfo)
    → accessToken = token
    → user = {user_id, username, role, ...}
    → localStorage 写入 token + user_info
    → 触发 loadFavorites()

Token 过期 (401):
  refreshToken()
    → POST /auth/refresh → 新 access_token
    → 更新 accessToken + localStorage
    → 失败 → logout()

登出:
  logout()
    → POST /auth/logout (清 Cookie)
    → accessToken = null, user = null
    → localStorage.removeItem('access_token')
    → localStorage.removeItem('user_info')
    → favoritesStore.reset()
    → router.push('/login')
```

#### `player` Store (`stores/player.ts`)

| 状态字段 | 类型 | 来源 | 持久化 |
|----------|------|------|--------|
| `currentTrack` | `Track \| null` | `play(track)` 调用 | `localStorage('player_last_track')` |
| `playlist` | `Track[]` | `play(track, tracks)` 第二参数 | 不持久化 |
| `currentIndex` | `number` | 播放列表中的位置 | 不持久化 |
| `isPlaying` | `boolean` | `play()`/`togglePlay()` | 不持久化 |
| `currentTime` | `number` | Audio `timeupdate` 事件 | 不持久化 |
| `duration` | `number` | Audio `loadedmetadata` 或 track.duration_ms | 不持久化 |
| `volume` | `number` | `setVolume()` | `localStorage('player_volume')` |

**状态流转**：
```
用户点击歌曲 → play(track, tracks)
  │
  ├── 初始化 Audio (仅首次)
  │   audio = new Audio()
  │   绑定 timeupdate / loadedmetadata / ended / error 事件
  │
  ├── 如果切换歌曲 → logPlayInteraction() 记录上一首
  │
  ├── 更新状态:
  │   currentTrack = track
  │   currentTime = 0
  │   duration = track.duration_ms / 1000
  │   localStorage('player_last_track') = JSON.stringify(track)
  │
  ├── 设置音频源:
  │   audio.src = /api/v1/tracks/{track_id}/preview
  │   audio.play()
  │   isPlaying = true
  │
  └── 播放中:
      timeupdate → currentTime 实时更新
      ended → logPlayInteraction() → next()

页面刷新:
  currentTrack = localStorage('player_last_track') 恢复
  volume = localStorage('player_volume') 恢复
  isPlaying = false（不自动恢复播放）
```

#### `favorites` Store (`stores/favorites.ts`)

| 状态字段 | 类型 | 来源 | 持久化 |
|----------|------|------|--------|
| `favoriteIds` | `Set<string>` | `loadFavorites()` API 响应 | 不持久化（登录后从 API 加载） |
| `loaded` | `boolean` | 加载完成标记 | 不持久化 |

**状态流转**：
```
登录成功 → loadFavorites()
  GET /users/me/favorites/ids → {track_ids: ["DZ123", "DZ456", ...]}
  → favoriteIds = new Set(track_ids)
  → loaded = true

点击收藏按钮 → toggleFavorite(trackId)
  1. 乐观更新: favoriteIds 立即 add/delete（UI 无延迟）
  2. API 调用: POST/DELETE /favorites/{trackId}
  3. 失败回滚: favoriteIds 恢复到操作前状态

登出 → reset()
  favoriteIds = new Set()
  loaded = false
```

### 5.3.3 前端 localStorage 键值表

| Key | 值类型 | 写入时机 | 读取时机 | 清除时机 |
|-----|--------|---------|---------|---------|
| `access_token` | JWT string | login/register 成功 | 每次请求注入 Header；导航守卫 | logout |
| `user_info` | JSON `{"user_id","username","role",...}` | login/register 成功 | App.vue 初始化恢复用户状态 | logout |
| `player_last_track` | JSON Track 对象 | 每次切换歌曲 | 应用启动时恢复播放器状态 | 不主动清除 |
| `player_volume` | string "0.8" | 音量变化时 | 应用启动时恢复音量 | 不主动清除 |

### 5.3.4 Cookie 键值表

| Key | 值类型 | 属性 | 写入时机 | 读取时机 | 清除时机 |
|-----|--------|------|---------|---------|---------|
| `refresh_token` | JWT string | HttpOnly, SameSite=Lax, Path=/api/v1/auth, Max-Age=604800 | login/register 成功 | POST /auth/refresh（浏览器自动携带） | logout 或过期 |
