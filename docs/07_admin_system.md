# 7. 管理系统架构 (Admin System Architecture)

## 7.1 管理系统概览

系统包含独立的管理端，用于数据管理、模型训练、评测和调度。管理端分为管理后端（FastAPI）和管理前端（Vue 3），与用户端完全隔离。

```
┌─────────────────────────────────────────────────────────────┐
│                     管理浏览器 (Browser)                     │
│  Vue 3 SPA · Pinia Store · SSE · Axios HTTP Client          │
└────────────┬───────────────────────────────┬────────────────┘
             │ HTTP (REST API)               │ SSE (Progress)
             │ /admin/*                      │ /admin/training/progress/{id}/stream
             ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Vite Dev Server (Port 14000)                │
│         反向代理: /admin → Admin Backend:19000               │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Admin Backend (Port 19000)              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐  │
│  │Auth API  │  │Data API  │  │Training   │  │Scheduler  │  │
│  │/admin/*  │  │/admin/data│  │API        │  │API        │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  │
│       │              │              │              │         │
│  ┌────▼──────────────▼──────────────▼──────────────▼─────┐  │
│  │          Admin Service Layer                          │  │
│  │  training_service · scheduler_service                  │  │
│  └────┬──────────────┬──────────────┬────────────────────┘  │
│       │              │              │                        │
│  ┌────▼─────┐  ┌─────▼──────┐  ┌───▼────────────────────┐  │
│  │  MySQL   │  │ APScheduler│  │   Training Progress     │  │
│  │  (ORM)   │  │  (Jobs)    │  │  (File-based + SSE)    │  │
│  └──────────┘  └────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 7.2 管理后端架构

### 目录结构

```
admin/                                    # [目录] 管理后端应用
├── __init__.py                           # 空文件
├── main.py                               # [入口] FastAPI 应用启动入口
├── dependencies.py                       # [DI] 管理员权限校验
├── api/                                  # [目录] API 路由层
│   ├── __init__.py                       # 空文件
│   ├── auth.py                           # [路由] 管理员登录
│   ├── tracks.py                         # [路由] 批量导入歌曲、Deezer/Jamendo API
│   ├── users.py                          # [路由] 批量导入用户
│   ├── interactions.py                   # [路由] 批量导入交互
│   ├── data.py                           # [路由] 触发 LastFM/合成数据生成
│   ├── training.py                       # [路由] 训练触发、进度 SSE、历史、版本
│   ├── scheduler.py                      # [路由] 定时任务 CRUD、阈值配置
│   └── status.py                         # [路由] 系统状态统计
└── services/                             # [目录] 业务逻辑层
    ├── __init__.py                       # 空文件
    ├── training_service.py               # [服务] 训练子进程编排、进度跟踪
    └── scheduler_service.py              # [服务] APScheduler 封装、任务持久化
```

### 核心 API 端点

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| POST | `/admin/auth/login` | 无 | 管理员登录（role='admin'校验） |
| GET | `/admin/status` | 必须 | 数据统计（用户数/歌曲数/交互数/模型状态） |
| POST | `/admin/data/lastfm` | 必须 | 触发 LastFM 1K 用户数据生成 |
| POST | `/admin/data/synthetic` | 必须 | 触发合成 60 用户数据生成 |
| POST | `/admin/training/preprocess` | 必须 | 启动数据预处理 |
| POST | `/admin/training/feature-engineering` | 必须 | 启动特征工程 |
| POST | `/admin/training/train-all` | 必须 | 顺序执行完整训练流程 |
| POST | `/admin/training/evaluate` | 必须 | 启动模型评测 |
| GET | `/admin/training/progress/{task_id}/stream` | 必须 | SSE 实时进度流 |
| GET | `/admin/training/history` | 必须 | 获取训练历史列表 |
| POST | `/admin/scheduler/schedule` | 必须 | 创建定时任务 |
| GET | `/admin/scheduler/jobs` | 必须 | 获取所有定时任务 |
| PUT | `/admin/scheduler/threshold` | 必须 | 更新数据阈值触发配置 |

## 7.3 管理前端架构

### 目录结构

```
admin-web/                               # [目录] Vue 3 管理前端
├── index.html                           # [入口] SPA 入口 HTML
├── package.json                         # [配置] NPM 依赖
├── vite.config.ts                       # [构建] Vite 配置：端口14000、/admin 代理
├── Dockerfile                           # [构建] 前端 Docker 镜像
└── src/                                 # [目录] 源代码目录
    ├── main.ts                          # [入口] Vue 应用创建
    ├── App.vue                          # [根组件] 路由视图
    ├── router/                          # [目录] 路由配置
    │   └── index.ts                     # [路由] 管理端路由定义
    ├── stores/                          # [目录] Pinia Store
    │   ├── auth.ts                      # [状态] 管理员鉴权
    │   ├── training.ts                  # [状态] SSE 连接管理、任务状态
    │   └── scheduler.ts                 # [状态] 定时任务 CRUD
    ├── api/                             # [目录] API 调用封装
    │   └── client.ts                    # [HTTP] Axios 实例
    ├── views/                           # [目录] 页面级视图
    │   ├── Dashboard.vue                # [页面] 仪表盘：统计 + 最近训练
    │   ├── DataImport.vue               # [页面] 数据导入管理
    │   ├── Training.vue                 # [页面] 训练控制 + SSE 实时日志
    │   ├── Scheduler.vue                # [页面] 定时任务管理
    │   └── Models.vue                   # [页面] 模型状态 + 评测对比 + 版本历史
    └── components/                      # [目录] 可复用组件
        ├── AppLayout.vue                # [组件] 侧边栏布局
        ├── StatCard.vue                 # [组件] 统计卡片
        ├── ProgressBar.vue              # [组件] 进度条
        ├── LogPanel.vue                 # [组件] 日志面板
        ├── StatusBadge.vue              # [组件] 状态徽章
        └── LogDialog.vue                # [组件] 日志对话框（日志+评测结果）

```

### 核心组件说明

#### AppLayout.vue - 侧边栏布局
- 固定宽度 220px 侧边栏
- 最大宽度 1200px 内容区
- 导航项：仪表盘、数据导入、训练、调度器、模型状态

#### Training.vue - 训练控制
- 训练按钮组（预处理、特征工程、各模型训练、评测）
- SSE 实时进度显示
- 训练历史列表
- LogDialog 集成（查看日志和评测结果）

#### Models.vue - 模型管理
- 模型可用性网格展示
- 评测指标对比表格
- 版本历史列表（支持手动提升）
- 每版本评测下拉选择

#### Scheduler.vue - 调度器管理
- 定时任务列表（Cron/Interval/Threshold）
- 任务创建/编辑/删除
- 数据阈值配置界面

## 7.4 共享包架构 (common/)

`common/` 目录包含用户后端和管理后端共享的代码，通过 Docker 卷挂载到两个容器中。

```
common/                                  # [目录] 共享包
├── __init__.py                          # 空文件
├── config.py                            # [配置] Pydantic Settings
├── database.py                          # [数据库] 异步引擎 + Session 工厂
├── core/                                # [目录] 核心模块
│   ├── __init__.py                      # 空文件
│   └── security.py                      # [安全] JWT 编解码、密码哈希
├── models/                              # [目录] SQLAlchemy ORM 模型
│   ├── __init__.py                      # 空文件
│   ├── user.py                          # [模型] users 表
│   ├── track.py                         # [模型] tracks 表
│   ├── artist.py                        # [模型] artists 表
│   ├── interaction.py                   # [模型] user_interactions 表
│   ├── track_feature.py                 # [模型] track_features 表
│   ├── tag.py                           # [模型] tags + track_tags 表
│   ├── offline_recommendation.py        # [模型] offline_recommendations 表
│   ├── user_favorite.py                 # [模型] user_favorites 表
│   ├── artist_favorite.py               # [模型] artist_favorites 表
│   ├── training_schedule.py             # [模型] training_schedules 表（调度器）
│   └── training_threshold_state.py      # [模型] training_threshold_state 表（阈值状态）
└── schemas/                             # [目录] Pydantic Schema
    ├── __init__.py                      # 空文件
    ├── artist.py                        # [Schema] 艺术家相关 Schema
    └── ...                              # [Schema] 其他共享 Schema
```

### 共享表说明

#### training_schedules 表
| 字段 | 类型 | 说明 |
|------|------|------|
| schedule_id | INT PK | 调度 ID |
| name | VARCHAR(100) | 任务名称 |
| task_type | VARCHAR(50) | 任务类型（train_all/evaluate） |
| trigger_type | VARCHAR(20) | 触发类型（cron/interval/threshold） |
| trigger_args | JSON | 触发参数 |
| enabled | BOOLEAN | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |

#### training_threshold_state 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | 主键 |
| last_interaction_count | INT | 上次训练时交互数 |
| last_check_time | TIMESTAMP | 上次检查时间 |

## 7.5 训练进度系统

### 进度文件结构

```
data/
├── training_progress/                   # [目录] 训练进度文件
│   ├── {task_id}.json                   # [文件] 任务进度（原子写）
│   └── ...
└── evaluation_progress/                 # [目录] 评测进度文件
    ├── {task_id}.json                   # [文件] 评测进度
    ├── {task_id}_report.json            # [文件] 评测结果报告
    └── ...
```

### 进度文件格式

```json
{
  "task_id": "20250421_123456_preprocess",
  "status": "running",
  "progress": 45,
  "message": "Processing user interactions...",
  "start_time": "2025-04-21T12:34:56Z",
  "logs": ["Starting preprocess...", "Loading data from MySQL..."]
}
```

### SSE 端点

```
GET /admin/training/progress/{task_id}/stream?token={jwt_token}
```

- 返回 `text/event-stream` 格式
- 每次进度更新推送事件
- 前端使用 `EventSource` 订阅
- 断线自动重连（最多 3 次）

## 7.6 定时调度系统

### APScheduler 集成

- 调度器类型：`AsyncIOScheduler`
- 启动时机：Admin Backend `lifespan` startup
- 任务持久化：MySQL `training_schedules` 表
- 并发控制：`max_instances=1`, `coalesce=True`

### 三种触发模式

| 模式 | 配置示例 | 说明 |
|------|---------|------|
| **Cron** | `{"cron": "0 2 * * *"}` | 每天凌晨 2 点执行 |
| **Interval** | `{"minutes": 60}` | 每 60 分钟执行一次 |
| **Threshold** | `{"interaction_delta": 100}` | 交互增量 ≥ 100 时触发 |

### 阈值检查机制

- 每 10 分钟检查一次
- 对比当前交互数 vs 上次训练时交互数
- 达到阈值时触发训练
- 更新 `training_threshold_state` 表
