# 3. 全景目录树与文件字典 (Directory Tree & File Dictionary)

## 3.1 完整目录树

```
music_rec/
├── app/                                    # [目录] FastAPI 后端应用主包
│   ├── __init__.py                         # 空文件，标记 app 为 Python 包
│   ├── main.py                             # [入口] FastAPI 应用启动入口，注册路由与中间件
│   ├── config.py                           # [配置] Pydantic Settings，从 .env 读取全部配置项
│   ├── database.py                         # [数据库] SQLAlchemy 异步引擎、Session 工厂、Base 基类
│   ├── generate_hash.py                    # [工具] 生成密码哈希的辅助脚本
│   ├── test_updater.py                     # [工具] 测试用的数据更新脚本
│   ├── Dockerfile                          # [构建] 后端 Docker 镜像定义，基于 python:3.11-slim
│   ├── api/                                # [目录] API 路由层，每个文件对应一组 REST 端点
│   │   ├── __init__.py                     # 空文件
│   │   ├── auth.py                         # [路由] 认证端点：注册、登录、刷新令牌、登出
│   │   ├── users.py                        # [路由] 用户端点：个人信息、修改资料、统计数据、收藏ID列表
│   │   ├── tracks.py                       # [路由] 歌曲端点：列表搜索、热门排行、单曲详情、音频代理
│   │   ├── interactions.py                 # [路由] 交互端点：记录行为事件、查询历史
│   │   ├── recommendations.py             # [路由] 推荐端点：获取个性化推荐 Feed
│   │   └── favorites.py                    # [路由] 收藏端点：收藏列表、添加收藏、取消收藏
│   ├── core/                               # [目录] 核心基础设施模块
│   │   ├── __init__.py                     # 空文件
│   │   ├── dependencies.py                 # [DI] FastAPI 依赖注入：获取当前用户、可选认证、管理员校验
│   │   ├── exceptions.py                   # [异常] 全局异常处理器，统一 JSON 错误格式
│   │   └── security.py                     # [安全] JWT 编解码、密码哈希/验证、双令牌生成
│   ├── models/                             # [目录] SQLAlchemy ORM 模型，一一对应数据库表
│   │   ├── __init__.py                     # 空文件
│   │   ├── user.py                         # [模型] users 表：用户ID、用户名、密码哈希、角色、年龄、性别、国家
│   │   ├── track.py                        # [模型] tracks 表：歌曲ID、标题、歌手、专辑、时长、播放数、状态、试听URL、封面URL
│   │   ├── interaction.py                  # [模型] user_interactions 表：交互ID、用户ID、歌曲ID、类型、评分、播放时长、完成度
│   │   ├── track_feature.py                # [模型] track_features 表：歌曲ID、danceability、energy、tempo、valence、acousticness
│   │   ├── tag.py                          # [模型] tags 表 + track_tags 表：标签名、歌曲-标签多对多关联
│   │   ├── offline_recommendation.py       # [模型] offline_recommendations 表：用户ID、推荐歌曲ID列表(JSON)、更新时间
│   │   └── user_favorite.py                # [模型] user_favorites 表：用户ID + 歌曲ID 联合主键
│   ├── schemas/                            # [目录] Pydantic 请求/响应 Schema
│   │   ├── __init__.py                     # 空文件
│   │   ├── auth.py                         # [Schema] RegisterRequest、LoginRequest、TokenResponse、RefreshResponse
│   │   ├── track.py                        # [Schema] TrackResponse、TrackListResponse、TrackSearchRequest
│   │   ├── interaction.py                  # [Schema] InteractionCreate(类型1-4)、InteractionResponse
│   │   ├── recommendation.py              # [Schema] RecommendationItem(含score)、RecommendationResponse(含strategy)
│   │   └── user.py                         # [Schema] UserProfile、UpdateProfileRequest
│   ├── services/                           # [目录] 业务逻辑层，被 API 路由调用
│   │   ├── __init__.py                     # 空文件
│   │   ├── auth_service.py                 # [服务] register_user、authenticate_user、generate_tokens
│   │   ├── track_service.py                # [服务] get_tracks(分页搜索)、get_track_by_id、get_popular_tracks
│   │   ├── interaction_service.py          # [服务] log_interaction(MySQL+Redis双写)、get_user_history、get_user_sequence_from_redis
│   │   └── recommendation_service.py      # [服务] get_recommendations(4级降级)、_ml_pipeline_recommend、cache_recommendations
│   └── utils/                              # [目录] 工具函数
│       └── __init__.py                     # [工具] Redis 单例客户端：get_redis()、close_redis()
├── ml_pipeline/                            # [目录] 机器学习管线，可被后端动态 import 或独立运行训练
│   ├── config.py                           # [配置] ML 超参数(EMBEDDING_DIM=64, HIDDEN_DIMS, LR等)与路径常量
│   ├── data_process/                       # [目录] 数据预处理与特征工程
│   │   ├── __init__.py                     # 空文件
│   │   ├── preprocess.py                   # [数据] 从 MySQL 加载交互数据 → 清洗 → 隐式标签生成 → 时序切分 → 存为 Parquet
│   │   ├── feature_engineering.py          # [特征] 构建用户特征(age_bucket/统计量)、物品特征(声学/流行度)、DeepFM数据集、负采样
│   │   └── generate_synthetic_data.py      # [数据] 生成 60 个合成用户(8种偏好原型)，每人 40-250 条交互行为
│   ├── models/                             # [目录] 推荐算法模型实现
│   │   ├── item_cf.py                      # [模型] ItemCF：构建 user-item 稀疏矩阵 → item间余弦相似度 → 推荐相似物品
│   │   ├── matrix_factorization.py         # [模型] SVD(BPR-MF)：PyTorch 实现，用户/物品 Embedding + 偏置，BPR 损失训练
│   │   ├── deepfm.py                       # [模型] DeepFM：一阶线性 + 二阶FM交叉 + 深度DNN，输出 sigmoid 概率，支持 ONNX 导出
│   │   └── sasrec.py                       # [模型] SASRec：单向 Transformer 建模用户序列，因果注意力预测下一首
│   ├── inference/                          # [目录] 在线推理管线
│   │   ├── __init__.py                     # 空文件
│   │   ├── recall.py                       # [推理] 多路召回：SASRec召回 + ItemCF召回 + Popularity补充，合并去重加权
│   │   ├── ranking.py                      # [推理] DeepFM 精排：构建稀疏/稠密特征矩阵 → 推理 → 70%DeepFM+30%召回分融合
│   │   └── pipeline.py                     # [推理] 推荐总入口：检查模型可用 → 选策略 → 调recall → 调ranking → 格式化输出
│   ├── training/                           # [目录] 模型训练脚本（离线执行）
│   │   ├── __init__.py                     # 空文件
│   │   ├── train_baseline.py              # [训练] 训练 ItemCF + SVD，评估并生成 baseline_report.md
│   │   ├── train_deepfm.py                # [训练] 训练 DeepFM 排序模型，评估 AUC/LogLoss，导出 ONNX
│   │   └── train_sasrec.py                # [训练] 训练 SASRec 序列模型，用训练序列前缀评估 Precision/Recall/NDCG
│   └── evaluation/                         # [目录] 评估指标
│       ├── __init__.py                     # 空文件
│       └── metrics.py                      # [评估] Precision@K、Recall@K、NDCG@K、HitRate@K、Coverage、格式化报告
├── data/                                   # [目录] 数据存储（运行时生成，不提交 Git）
│   ├── models/                             # [目录] 训练好的模型文件
│   │   ├── baseline_report.md              # [输出] ItemCF 和 SVD 的评测报告 Markdown
│   │   ├── item_cf/                        # [目录] ItemCF 模型文件
│   │   ├── svd/                            # [目录] SVD 模型文件
│   │   ├── deepfm/                         # [目录] DeepFM 模型文件(.pt + .onnx + meta.json)
│   │   └── sasrec/                         # [目录] SASRec 模型文件(.pt + meta.json)
│   ├── processed/                          # [目录] 预处理后的 Parquet 数据文件
│   └── raw/                                # [目录] 原始数据（本项目未使用，预留）
├── frontend/                               # [目录] Vue 3 前端应用
│   ├── index.html                          # [入口] SPA 入口 HTML，引入 Google Fonts (Inter)
│   ├── package.json                        # [配置] NPM 依赖：vue3, pinia, vue-router, axios, vite
│   ├── vite.config.ts                      # [构建] Vite 配置：端口13000、@别名、/api 代理
│   ├── tsconfig.json                       # [配置] TypeScript 编译选项
│   ├── tsconfig.app.json                   # [配置] App 专用 TS 配置
│   ├── tsconfig.node.json                  # [配置] Node 环境专用 TS 配置
│   ├── env.d.ts                            # [类型] Vite 环境变量类型声明
│   ├── Dockerfile                          # [构建] 前端 Docker 镜像，基于 node:20-alpine，npm run dev
│   ├── public/                             # [目录] 静态资源（直接复制到输出）
│   │   └── vite.svg                        # [静态] Favicon SVG 图标
│   └── src/                                # [目录] 源代码目录
│       ├── main.ts                         # [入口] Vue 应用创建：createApp → Pinia → Router → mount('#app')
│       ├── App.vue                         # [根组件] 布局骨架：左侧 Sidebar + 中间 router-view + 底部 PlayerBar
│       ├── router/                         # [目录] 路由配置
│       │   └── index.ts                    # [路由] 6条路由定义 + beforeEach 导航守卫(登录态校验)
│       ├── stores/                         # [目录] Pinia 全局状态 Store
│       │   ├── auth.ts                     # [状态] 鉴权：token、用户信息、login/register/refreshToken/logout
│       │   ├── player.ts                   # [状态] 播放器：当前曲目、播放列表、Audio元素、进度、音量、行为上报
│       │   └── favorites.ts                # [状态] 收藏：favoriteIds(Set)、loadFavorites、toggleFavorite(乐观更新)
│       ├── api/                            # [目录] API 调用封装
│       │   ├── client.ts                   # [HTTP] Axios 实例：baseURL=/api/v1、JWT 注入拦截器、401 自动刷新拦截器
│       │   ├── auth.ts                     # [API] authApi：register、login、refresh、logout
│       │   └── tracks.ts                   # [API] tracksApi、recommendationsApi、interactionsApi、favoritesApi、usersApi
│       ├── types/                          # [目录] TypeScript 类型定义
│       │   └── index.ts                    # [类型] Track、User、TokenResponse、RecommendationResponse、InteractionCreate
│       ├── views/                          # [目录] 页面级视图组件
│       │   ├── Home.vue                    # [页面] 首页：推荐卡片网格 + 热门排行列表
│       │   ├── Login.vue                   # [页面] 登录：用户名/密码表单 → auth.login()
│       │   ├── Register.vue                # [页面] 注册：用户名/密码/确认/年龄/性别/国家表单 → auth.register()
│       │   ├── Discover.vue                # [页面] 发现：搜索框 + 歌曲列表 + 分页
│       │   ├── Profile.vue                 # [页面] 个人中心：用户头像/信息、修改资料表单、统计卡片
│       │   └── Favorites.vue               # [页面] 收藏：收藏歌曲列表
│       ├── components/                     # [目录] 可复用组件
│       │   ├── common/                     # [目录] 通用组件
│       │   │   └── TrackCard.vue           # [组件] 歌曲卡片：封面、标题、歌手、时长、收藏按钮、点击播放
│       │   ├── layout/                     # [目录] 布局组件
│       │   │   └── Sidebar.vue             # [组件] 侧边栏导航：Logo、5个导航项(按登录态动态显示)、用户信息/登出
│       │   └── player/                     # [目录] 播放器组件
│       │       └── PlayerBar.vue           # [组件] 底部播放栏：进度条、曲目信息、上/播/下控制、时间、音量
│       └── assets/                         # [目录] 静态资源
│           ├── main.css                    # [样式] 全局 CSS 变量与基础样式（暗色主题、间距、渐变、动画）
│           ├── hero.png                    # [图片] 首页 Hero 图片（如有）
│           ├── vite.svg                    # [图标] Vite Logo
│           └── vue.svg                     # [图标] Vue Logo
├── db/                                     # [目录] 数据库初始化脚本
│   └── init.sql                            # [SQL] 建表 DDL：7张表 + 索引 + 外键，Docker 启动时自动执行
├── scripts/                                # [目录] 运维与调试脚本
│   ├── seed_data.py                        # [脚本] 种子数据：从 Deezer API 抓取 8 个流派各 30 首歌 + 创建 admin 用户
│   ├── check_db.py                         # [脚本] 检查数据库连接与表状态
│   ├── debug_svd.py                        # [脚本] 调试 SVD 模型推理
│   ├── debug_uid.py                        # [脚本] 调试用户 ID 映射
│   ├── fix_admin.py                        # [脚本] 修复 admin 用户密码
│   └── test_api.py                         # [脚本] API 端点冒烟测试
├── shared_contracts/                       # [目录] 共享契约（预留，当前为空）
├── docs/                                   # [目录] 系统文档
├── .env                                    # [配置] Docker Compose 使用的环境变量（含密码、端口映射）
├── .env.example                            # [配置] 环境变量模板，新开发者复制为 .env 使用
├── .gitignore                              # [配置] Git 忽略规则
├── docker-compose.yml                      # [编排] 5 个服务容器编排：MySQL、Redis、Backend、Seeder、Frontend
├── pyproject.toml                          # [配置] Python 项目元数据 + 依赖声明 + uv 配置
├── requirements.txt                        # [配置] pip 格式依赖锁定文件（Docker 构建使用）
├── uv.lock                                 # [锁文件] uv 精确依赖版本锁定
└── README.md                               # [文档] 项目说明文档
```

## 3.2 文件数量统计

| 目录 | 文件数 | 职责 |
|------|--------|------|
| `app/` | 24 | 后端全部代码（路由、模型、服务、Schema、配置） |
| `app/api/` | 6 | REST API 端点定义 |
| `app/models/` | 7 | ORM 模型（对应 7 张数据库表） |
| `app/schemas/` | 5 | Pydantic 请求/响应校验模型 |
| `app/services/` | 4 | 业务逻辑实现 |
| `ml_pipeline/` | 16 | ML 管线（数据处理、模型、训练、推理、评估） |
| `frontend/src/` | 22 | 前端全部源码 |
| `scripts/` | 6 | 运维/调试脚本 |
| 根目录配置文件 | 8 | Docker、依赖管理、环境变量 |
| **总计** | **~93** | |
