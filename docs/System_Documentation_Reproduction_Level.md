# 音乐推荐系统 (MusicRec) - 极限复现级重定义全视角白皮书

> ⚠️ **最高级别重载警告**：应最高重构要求，本文档彻底摒弃任何抽象层描述。这是整个工程的**穷尽级源码物理还原镜像**。如果你没有任何代码基础，只需严格遵循此文，复制文档中拆解出的生命流向逻辑公式及文件拓扑，便能将项目如同 3D 打印一般在你的机器上从零到一完全写出来。

---

## 1. 物理目录结构穷举与全景字典 (The Exhaustive Dictionary)

本系统共有四个主要业务根目录：`app`, `frontend`, `ml_pipeline`, `scripts`。以下是将整个项目近百个文件抽丝剥茧的绝对字典。

### 1.1 `app/` - FastAPI 服务核心矩阵
这里负责路由收发与会话流转，所有的 `.py` 除了被 `main.py` 调度外相互保持解耦。
- **`main.py`**：【基座层】系统 `0.0` 入口。定义了 FastAPI() 实例，包含 `CORSMiddleware` (允许 `localhost:13000` 及 `3000` 跨域)，同时暴露 `@app.get("/health")`。最核心的机制是定义的 `lifespan`：它拦截了整个系统启动时连接挂载并在关闭时强制挂起 `await close_redis()`，切断游标池。
- **`config.py`**：【环境投射器】利用 `pydantic-settings` 里的 `BaseSettings` 把系统外挂的 `.env` 里的 `MYSQL_HOST`, `REDIS_PASSWORD` 转为强类型的 Python 内存字典。
- **`database.py`**：【数据引擎】使用 `sqlalchemy.ext.asyncio.create_async_engine` 缔结到 MySQL。提供了一个 `yield` 生成器：`get_db()`。保证每一个进入系统的并发网络请求，独占独立的 AsyncSession 事务。
- **`api/` (路由层)**：
  - `auth.py`：暴露出 `/login`。直接读取 Request Body，调用 `auth_service.py` 查表比对后，下发封装的 `{access_token: xxx}` 给前端。
  - `recommendations.py`：系统的金字塔顶端点 `/feed`。它接纳 `size` (默认20)、`scene` (如 home_feed) 作为查询参数，通过 Header JWT 获取 `user_id` 后，投递给 `recommendation_service` 排列。
  - `interactions.py`：【高频记录仪】前端每次听歌播放时间达标、跳过、点赞，调用 `/log` 或 `/beacon`。不仅存入 MySQL `user_interactions` 表，更致命的一步是：同步在 Redis 产生对该用户的 `lpush user:seq:{user_id} track_id` 并 `ltrim 0 49`，维持推荐流水线需要的五十条“活水”。
  - `favorites.py` / `tracks.py` / `users.py`：基础库表的增删改查端口，供点赞或查询流行歌曲接口。
- **`core/` (算法工具层)**：
  - `security.py`：内部含有 `pwd_context = CryptContext(schemes=["bcrypt"])`。一切密码相关的加密、比对由此发放；提供 `create_access_token` 生成 1 星期有效期的双载荷 JWT 凭据。
  - `dependencies.py`：利用 `Depends()` 抽取 HTTP 请求里的凭证。验证、解码载荷后提取 user_id。
- **`services/` (行为控制器)**：
  - `recommendation_service.py`：真正的灵魂指挥手，将在此后章节详写（含四段防崩塌机制）。
- **`schemas/`**: Pydantic 数据规范文件，如 `recommendation.py` 严格规范输出带有 `strategy_matched`, `items` (List) 的对象，绝不让脏类型返回给前端。
- **`models/`**: 包含 ORM 结构： `track.py`, `user.py`, `offline_recommendation.py` 等与底座 `db/init.sql` 对映的对象关系构建层。

### 1.2 `frontend/` - Vue 3 前端视窗矩阵
前端摒弃了庞大的 Vuex，全部拥抱 Composition API，极度关注毫秒级交互体验。
- **`src/main.ts`**：执行 `createApp(App)`，把 `createPinia()` 和 `router` 挂载在 `#app` 这个 DOM 坑位上。
- **`src/api/client.ts`**：【通信网关】。非常惊艳的地方在于它的响应拦截器：当接收到 HTTP `401 Unauthorized` 时，如果不属于登录接口，它会调用 Pinia 里的 `auth.refreshToken()`；并且内置了熔断器——如刷新同样抛 401 直接登出，绝不让应用陷入无限刷新的黑洞。
- **`src/stores/` (状态反应堆)**：
  - `auth.ts`：将 token 放进 `localStorage` 持久化，并且将解密后的 user_id、role 进行内存级维持。
  - `player.ts`：整个前端的机械心脏。创建原生 `HTMLAudioElement` 对象侦听播放事件(`timeupdate`)。在歌曲 `ended` 或人工跳歌时推算目前的秒数，如时长大于阈值，则暗中向 `/api/v1/interactions/log` 发射交互。
- **`src/views/Home.vue` 等组件**：
  - `Home.vue`：它挂载时并行发射 `Promise.all` 去拉 `/api/v1/recommendations/feed` (20首每日推荐) 和 `/api/v1/tracks/popular` (10首兜底热歌)。通过双路 v-for 交给子组件呈现。
  - `Discover.vue`, `Login.vue`, `Profile.vue` 等等用于管理系统的分支。
- **`src/components/common/TrackCard.vue`**：卡片单元件。
- **`src/components/player/PlayerBar.vue`**：负责呈现 `player.ts` 底层的进度条模拟界面。

### 1.3 `ml_pipeline/` - 脑机推荐算力域
如果说前端与后端是骨架，这里便是项目运作的神经网络。
- **`inference/pipeline.py`**：【神经节并流场】。它暴露给外层后端的唯一入口 `recommend(user_id, user_sequence...)`：
  在代码里通过 `any(models.values())` 检验磁盘 `MODEL_DIR` 是否拥有模型。然后：
  1. 调用同级的 `recall.py -> multi_recall` 分流计算。
  2. 调用同级的 `ranking.py -> rank_candidates` 做矩阵整合计算。
- **`inference/recall.py`**：【千人千召回】
  利用缓存中取出的 `sasrec_model` 根据你的 `seq` 召唤出与你过往共振过的 150 首歌；再利用 `item_cf.py` 基于全局图网矩阵拿 150 首；再补上热力榜 50 首。随后在 Dictionary `candidates` 中进行分值缩放去重 (如果两边同时召回，ItemCf 给的权重为 0.5 叠加给 SASRec 原有得分为奖励值)。
- **`inference/ranking.py`**：【血腥格斗场(深排)】
  拿到了召回的近 300 首歌，结合利用通过执行的 `data_process` 提取出存入磁盘的 `user_features.parquet` 和 `item_features.parquet`，拼出一条 `[用户年龄, 舞蹈点... 歌曲BPM...]` 等特征集合。生成 `numpy.int64` 稀疏举证和 `numpy.float32` 稠密矩阵并输入到 `_deepfm.predict()` 模型！最后拿到最终对比如 0.88 可信度的保留率切分前 20。
- **`models/item_cf.py`**：【余弦图网矩阵】它是通过 `sklearn.metrics.pairwise import cosine_similarity` 将 N 位用户的点击与评分，转成巨大特征向量。对各个物品求取点积相似。以 `np.save` 写在 `item_sim_matrix.npy` 里随时备查。
- **`models/deepfm.py`, `sasrec.py`**：构建真实的张量神经网络的原始蓝图拓扑图（如 Embedding / DNN 等）。
- **`data_process/generate_synthetic_data.py`**：【灵魂赋予工厂】对于测试环境空机器，这是从 0 创造生态的代码。包含一个向空数据库生成 60 个基础用户，并基于强弱高斯模拟函数让不同风格偏好的人产生超过 30 万跳假行为的伪造动作链器，以免所有训练矩阵全是 0 而奔溃报错。

---

## 2. 深度重现：核心大动脉级生命体代码复刻

如果你要徒手从原始字符串结构构建核心逻辑，必须要彻底参透以下极高危代码段的还原理念与算式公式！

### 2.1 后端生命线 `recommendation_service.get_recommendations()`
```python
# 防护段 L1：Redis 强隔离缓冲网络 (防过穿)
redis = await get_redis()
cached = await redis.get(f"rec:user:{user_id}")
if cached:
    # 命中就立即切断不耗费CPU
    data = json.loads(cached)
    return {"strategy_matched": data.get("strategy"), "items": data["items"]}

# 进展段 L2：当 Redis Key Miss，调模型。
# 下钻至 interaction 设下的伏笔，获取最新 50 个记录特征列表。
seq = await redis.lrange(f"user:seq:{user_id}", 0, 49) 
# 把这 50 个特征串通过 ML API 处理
ml_result = ml_recommend(user_sequence=seq, top_k=20) 
```

### 2.2 前端心跳线 `player.ts -> logPlayInteraction()`
如果不触发这段代码，整套系统就是摆设。
```typescript
function logPlayInteraction() {
  // 把播放器的当前进度条模拟或真音轨拿出来，转毫秒
  const playDurationMs = Math.floor(currentTime.value * 1000)
  if (playDurationMs < 1000) return // 如果这用户是乱刷的一秒内立刻切歌，当做脏噪音废弃

  // 通过底层 axios 层级 api 推向后端。
  interactionsApi.log({
    track_id: currentTrack.value.track_id, // 发给谁的？
    interaction_type: 1, // '1'代表着正向播放动作标签
    play_duration: playDurationMs // 模型后续会将该变量除以歌的长用于构建 'completion_rate' 作为评分！
  })
}
```

### 2.3 核心血肉线：模型 `item_cf.py -> fit()` 核心矩阵生成解构
它是怎么将全站的行为动作（日志记录）转为高纬空间距离的？
```python
# 从原始 interaction 数据中抽出仅仅具有 1 号标记（发生过播放）的人与歌！
positive = interactions[interactions["label"] == 1]

# 组拼一个坐标体系
user_indices = positive["user_idx"].values
item_indices = positive["track_idx"].values
values = positive["completion_rate"].fillna(1.0).values  # 把听歌完成率当做评价权重！

# 极度暴力的降维打发，构建超级稀疏数组 csr 节省千万级内存爆破
self.user_item_matrix = csr_matrix((values, (user_indices, item_indices)))

# 高能反应核心 —— 强制对以 track(歌曲) 为主轴的方向进行相关分析
# 任何听 A 的人也都极度爱听 B，系统即对这两首歌生成极其趋近 1.0 的关系标尺
self.item_sim_matrix = cosine_similarity(self.user_item_matrix.T)
np.fill_diagonal(self.item_sim_matrix, 0) # 清除本体 1 的干扰
```

---

## 3. 防逆重构、雷区警告与脱水实境指南（100%成功率避坑极旨）

不论是谁，照着上述蓝图还原后如果报错瀑布流，那绝对出自这两个死亡断口区：

### 💣 第 1 雷：哈希崩盘校验灾难 (已修复但在重构需极度警告)
**深层内因 (代码视角)**：`app/core/security.py` 中的 `pwd_context.verify()` 调用的 passlib（底层为 C 语言基于定长的密码原语算法）。你哪怕在任意一条 python 环境脚本当中的某个 `password_hash` 前缀、主体、结尾（包含换行折叠误操作）导致了总体长度不在整好 `60` 位上字符（本站中测试用账户生成为 `$2b$12...` 构架形式的长链）。这会在启动系统验证查询时当场触发 `ValueError: malformed bcrypt hash (checksum must be exactly 31 chars)`，从而将你的核心 API 端点锁死并造成 `500` 全站拒绝登录灾难！
**修复方针**：永远用正经生成器产生定长散列！任何字符串赋值与生成长度差一丝一毫都将失败。

### 💣 第 2 雷：无限 401 自毁灭请求攻击循环
**深层内因 (代码视角)**：`frontend/src/api/client.ts` 拦截器里的恶性死锁。如果用户正在登录系统并进行听歌，此时 access 凭证和 refresh 凭证**同时物理自然失效**，后端向该播放操作掷回 `401 Unauthorized`。前端拦截器接管后进行“静默自修复”，向 `/auth/refresh` 请求恢复票据——但尴尬的是，由于连带有这把刷新钥匙也过期了，后端再次针对这个修复操作扔出新一个 `401`。如果你在此处漏写了 `!originalRequest.url.includes('/auth')` 条件把登录态过滤出去。系统框架将反复向刷新端口疯狂递送重复的修复请求直到客户端游标线程池被自我 DDOS 挤崩。
**修复方针**：确保 axios interceptor 的 error catch 里将相关授权 API 的 retry 做短路绝不继续处理！
