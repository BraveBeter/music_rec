<div align="center">
  <h1>个性化音乐推荐系统</h1>
  <p>包含完整推荐链路、多级容灾降级、管理后台与模型评测的工业级个性化音乐推荐引擎</p>

  <p>
    <img src="https://img.shields.io/badge/Frontend-Vue%203%20%7C%20Vite-42b883?style=flat-square&logo=vuedotjs" alt="Vue 3">
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/Database-MySQL%20%7C%20Redis-4479A1?style=flat-square&logo=mysql" alt="DB">
    <img src="https://img.shields.io/badge/AI-SASRec%20%7C%20DeepFM-EE4C2C?style=flat-square&logo=pytorch" alt="AI">
  </p>
</div>

---

## 项目简介

工业级推荐架构并非简单调用一个深度学习黑盒算法，而是囊括**召回、排序、重排**和降级防抖的高可用系统。

本项目利用 FastAPI 原生异步机制搭配 Vue 3 构建强交互前台，融合从流行度冷启动、离线托底到多路召回（ItemCF + SASRec + Tag + Genre-Popularity）与深度模型排序（DeepFM）的全栈式混合推荐管线，并使用 MMR 多样性重排提升推荐体验。系统还包含完整的管理后台，支持实时训练可视化、模型评测对比、定时调度等功能。

## 核心特性

- **异步全栈**：基于 `aiomysql` 的连接池全面解耦 I/O 阻塞，Redis `LPUSH` 实现毫秒级听歌历史序列构建
- **多路召回 + 深度排序**：整合 ItemCF（协同过滤）、SASRec（自注意力序列）、Tag-based、Genre-aware 多路召回，DeepFM 精排 + MMR 多样性重排
- **四级降级兜底**：Redis 缓存 → ML 实时推演 → 离线预计算 → 全球热榜冷启动
- **管理后台**：侧边栏布局，支持数据导入、实时训练进度（SSE）、模型评测指标对比、定时调度（Cron/Interval/阈值触发）
- **多数据源**：Deezer 30s 试听、Jamendo 完整流媒体、LastFM 1K 真实用户数据、合成数据生成器
- **曲风浏览与歌手系统**：按曲风随机推荐/热榜排行、歌手详情页、收藏管理

## 技术栈

| 模块 | 技术选型 | 说明 |
| :---: | :---: | :--- |
| **用户前端** | Vue 3 + Vite + Pinia | Composition API，Composition API，深色主题播放器 |
| **管理前端** | Vue 3 + Vite + Pinia | 侧边栏布局，SSE 实时进度，模型评测对比 |
| **用户后端** | FastAPI + SQLAlchemy | JWT 认证，异步 I/O，音频代理 |
| **管理后端** | FastAPI + APScheduler | 训练编排，SSE 进度流，定时调度 |
| **数据库** | MySQL 8 + Redis 7 | MySQL 持久存储，Redis 缓存 + 序列 |
| **ML 管线** | PyTorch + Scikit-learn | ItemCF, SASRec, DeepFM, 特征工程, 评测框架 |

---

## 快速开始

### 前提条件

- Git
- Docker Engine + Docker Compose

### 1. 克隆与清理

```bash
git clone https://gitee.com/BraveBeter/music_rec.git
cd music_rec

# 清空可能残留的容器和卷
docker-compose down -v --remove-orphans
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

### 3. 启动服务

```bash
docker-compose up -d --build
```

服务端口：
- `13000` — 用户前端
- `14000` — 管理前端
- `18000` — 用户后端
- `19000` — 管理后端
- `13307` — MySQL
- `16379` — Redis

Admin 后端启动时自动建表并创建管理员账号，无需 seeder 容器。

### 4. 开始使用

1. 访问 **http://127.0.0.1:14000** 进入管理后台
2. 使用 `.env` 中配置的管理员账号登录
3. 导入数据（Jamendo/Deezer/LastFM/合成数据）
4. 执行预处理 → 特征工程 → 模型训练 → 模型评测
5. 访问 **http://127.0.0.1:13000** 体验推荐系统

---

## 推荐架构

```
用户请求 → Redis 缓存 (L1)
         → ML 实时推演 (L2)
            ├─ 多路召回: SASRec + ItemCF + Tag-based + Genre-Popularity
            ├─ DeepFM 精排 (70% 权重) + 召回分数 (30% 权重)
            └─ MMR 多样性重排 (每曲风上限 3 首)
         → 离线预计算 (L3)
         → 热榜冷启动 (L4)
```

## 管理后台功能

| 功能 | 说明 |
| :--- | :--- |
| Dashboard | 系统概览：统计卡片、模型状态、最近训练/评测记录 |
| 数据导入 | Jamendo 全曲流媒体、Deezer 30s 试听、LastFM 1K 用户、合成数据 |
| 模型训练 | 实时 SSE 进度可视化（Epoch 进度条、Loss 值、日志流）、训练历史、日志弹窗 |
| 定时调度 | Cron 表达式 / 固定间隔 / 数据量阈值三种触发模式 |
| 模型状态 | 模型可用性、评测指标对比表（P@K, R@K, NDCG@K, HR@K, Coverage）、评测历史 |

## 本地开发

```bash
# 后端
uv run uvicorn app.main:app --reload                    # 用户后端
uv run uvicorn admin.main:app --reload --port 8001      # 管理后端

# 前端
cd frontend && npm run dev       # 用户前端 (port 5173)
cd admin-web && npm run dev      # 管理前端 (port 5174)

# ML 训练与评测
uv run python -m ml_pipeline.data_process.preprocess
uv run python -m ml_pipeline.data_process.feature_engineering
uv run python -m ml_pipeline.training.train_baseline     # ItemCF + SVD
uv run python -m ml_pipeline.training.train_sasrec       # SASRec
uv run python -m ml_pipeline.training.train_deepfm       # DeepFM
uv run python -m ml_pipeline.evaluation.evaluate_trained # 评测全部已训练模型
```

---

> *本项目基于工业界推荐落地场景搭建，适用于学习、毕业设计与小微工业化起步实践。*
