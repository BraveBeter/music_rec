# 1. 项目全景概览 (Project Overview)

## 1.1 项目定位

**MusicRec** 是一个基于深度学习的个性化音乐推荐系统，融合 ItemCF 协同过滤、SASRec 序列模型、DeepFM 排序模型等多种推荐策略，提供从用户注册、音乐浏览试听、行为采集到实时个性化推荐的完整闭环体验。系统包含独立的用户端和管理端，支持模型版本管理、自动评测对比、定时调度训练等企业级功能。

---

## 1.2 核心技术栈

### 后端 (Backend)

| 技术 | 版本 | 在本项目中的具体用途 |
|------|------|---------------------|
| **Python** | >=3.11 | 后端与ML管线的主语言 |
| **FastAPI** | 0.115.0 | 异步 Web 框架，处理所有 REST API 请求，提供自动 OpenAPI 文档 (`/docs`) |
| **Uvicorn** | 0.30.0 | ASGI 服务器，以 `--reload` 模式运行 FastAPI 应用 |
| **SQLAlchemy** | 2.0.35 | 异步 ORM，通过 `aiomysql` 驱动连接 MySQL，所有数据库操作通过 `AsyncSession` 执行 |
| **aiomysql** | 0.2.0 | MySQL 异步驱动，被 SQLAlchemy 用于异步数据库 I/O |
| **PyMySQL** | 1.1.1 | MySQL 同步驱动，用于数据预处理管线（`preprocess.py`）中的同步数据库读取 |
| **MySQL** | 8.0 | 主数据库，存储用户、歌曲、交互行为、标签、离线推荐等全部持久化数据 |
| **Redis** | 7-alpine | 缓存层：存储推荐结果缓存（30分钟TTL）、用户播放序列滑动窗口（SASRec输入） |
| **Pydantic** | 2.9.0 | 请求/响应数据校验，`BaseModel` 定义所有 API Schema |
| **pydantic-settings** | 2.5.0 | 从 `.env` 文件加载配置到 `Settings` 类 |
| **python-jose** | 3.3.0 | JWT Token 编解码（HS256算法），实现 Access Token + Refresh Token 双令牌鉴权 |
| **passlib + bcrypt** | 1.7.4 / 3.2.2 | 用户密码哈希与验证 |
| **httpx** | 0.27.0 | 异步 HTTP 客户端，用于代理 Deezer CDN 音频流和调用 Deezer API 获取签名 URL |

### 机器学习 (ML Pipeline)

| 技术 | 版本 | 在本项目中的具体用途 |
|------|------|---------------------|
| **PyTorch** | >=2.0.0 | DeepFM 排序模型、SASRec 序列模型、SVD 矩阵分解模型的训练与推理引擎 |
| **ONNX Runtime** | >=1.24.4 | DeepFM 模型导出为 ONNX 格式后的高性能推理（可选，替代 PyTorch 推理） |
| **NumPy** | 1.26.4 | 数值计算：ItemCF 相似度矩阵、评分数组操作 |
| **Pandas** | 2.2.2 | 数据处理：Parquet 文件读写、特征工程、数据清洗 |
| **scikit-learn** | 1.5.1 | MinMaxScaler 特征归一化、LabelEncoder 标签编码、cosine_similarity 余弦相似度 |
| **FAISS** | >=1.13.2 | 向量相似性搜索库（SVD 模型的 item embeddings 索引，预留用途） |
| **PyArrow** | >=23.0.1 | Parquet 文件格式的底层读写引擎 |

### 前端 (Frontend)

#### 用户前端 (`frontend/`)
| 技术 | 版本 | 在本项目中的具体用途 |
|------|------|---------------------|
| **Vue 3** | ^3.5.30 | 前端框架，全部使用 Composition API (`<script setup>`) |
| **TypeScript** | ~5.9.3 | 类型安全，所有 `.ts` 和 `.vue` 文件均使用 TypeScript |
| **Vite** | ^8.0.1 | 构建工具与开发服务器，配置 API 代理将 `/api` 转发到后端 |
| **Pinia** | ^3.0.4 | 全局状态管理：`auth`（鉴权）、`player`（播放器）、`favorites`（收藏）三个 Store |
| **Vue Router** | ^4.6.4 | SPA 路由，6 条路由带导航守卫（登录态校验） |
| **Axios** | ^1.14.0 | HTTP 客户端，封装了 JWT Token 自动注入和 401 自动刷新拦截器 |
| **@vueuse/core** | ^14.2.1 | Vue 组合式工具库（项目中已安装，用于辅助开发） |

#### 管理前端 (`admin-web/`)
| 技术 | 版本 | 在本项目中的具体用途 |
|------|------|---------------------|
| **Vue 3** | ^3.5.30 | 前端框架，Composition API |
| **TypeScript** | ~5.9.3 | 类型安全 |
| **Vite** | ^8.0.1 | 构建工具，API 代理转发到管理后端 |
| **Pinia** | ^3.0.4 | 状态管理：`auth`、`training`（SSE连接）、`scheduler` |
| **Vue Router** | ^4.6.4 | SPA 路由，包含仪表盘、数据导入、训练、调度器、模型页面 |
| **Axios** | ^1.14.0 | HTTP 客户端 |
| **EventSource** | 原生 API | SSE 训练进度实时订阅 |

### 基础设施 (Infrastructure)

| 技术 | 用途 |
|------|------|
| **Docker** | 容器化部署，每个服务独立容器 |
| **Docker Compose** | 编排 5 个容器：MySQL、Redis、Backend、Seeder、Frontend |
| **uv** | Python 包管理器（替代 pip），通过 `pyproject.toml` 管理依赖 |

---

## 1.3 环境依赖

| 依赖项 | 要求 | 说明 |
|--------|------|------|
| **Python** | >= 3.11 | 后端和 ML 管线运行所需 |
| **Node.js** | >= 20 | 前端开发与构建（Dockerfile 使用 `node:20-alpine`） |
| **Docker** | >= 20.0 | 容器化部署（推荐方式） |
| **Docker Compose** | >= 2.0 | 服务编排 |
| **Git** | 任意版本 | 代码版本管理 |
| **uv**（可选） | 最新版 | 如需在宿主机直接运行后端，推荐使用 `uv` 管理 Python 依赖 |

### 端口映射

| 服务 | 容器内端口 | 宿主机映射端口 | 说明 |
|------|-----------|--------------|------|
| MySQL | 3306 | 13307 | 避免与本地 MySQL 3306 冲突 |
| Redis | 6379 | 16379 | 避免与本地 Redis 6379 冲突 |
| 用户 Backend | 8000 | 18000 | 用户后端服务 |
| 管理 Backend | 8001 | 19000 | 管理后端服务 |
| 用户 Frontend (dev) | 3000 | 13000 | 用户前端界面 |
| 管理 Frontend (dev) | 3000 | 14000 | 管理前端界面 |
