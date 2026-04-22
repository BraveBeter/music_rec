# 8. 模型版本管理系统 (Model Versioning System)

## 8.1 版本管理概览

模型版本管理系统提供了模型训练的版本控制、自动评测对比和自动提升机制。每次训练都会保存版本化副本，通过 NDCG@10 指标对比决定是否提升到生产环境。

### 设计目标

1. **版本隔离**：每个训练版本独立存储，互不干扰
2. **自动提升**：新版本优于当前生产版本时自动提升
3. **手动干预**：管理员可手动提升任意版本到生产
4. **自动清理**：保留最近 N 个版本（默认 3 个），自动清理旧版本
5. **独立评测**：支持对任意历史版本进行评测

## 8.2 存储结构

### 目录结构

```
data/
├── models/                               # [目录] 生产模型目录（推理加载路径）
│   ├── item_cf/                          # [目录] ItemCF 生产模型
│   │   ├── item_sim_matrix.npy
│   │   ├── user_item_matrix.npz
│   │   ├── user2idx.parquet
│   │   ├── track2idx.parquet
│   │   └── meta.json
│   ├── svd/                              # [目录] SVD 生产模型
│   ├── deepfm/                           # [目录] DeepFM 生产模型
│   └── sasrec/                           # [目录] SASRec 生产模型
└── model_versions/                       # [目录] 版本化模型存储
    ├── item_cf/
    │   ├── 20250421_123456/              # [目录] 版本 ID（时间戳）
    │   │   ├── item_sim_matrix.npy
    │   │   └── meta.json
    │   ├── 20250422_150000/
    │   └── ...
    ├── svd/
    ├── deepfm/
    └── sasrec/
```

### 注册表文件

`data/model_registry.json` — 模型版本注册表

```json
{
  "primary_metric": "ndcg@10",
  "keep_versions": 3,
  "models": {
    "item_cf": {
      "active_version": "20250421_123456",
      "versions": {
        "20250421_123456": {
          "status": "active",
          "saved_at": "2025-04-21T12:34:56Z",
          "promoted_at": "2025-04-21T12:35:00Z",
          "metrics": {
            "ndcg@10": 0.0842,
            "precision@10": 0.0125,
            "recall@10": 0.0456
          }
        },
        "20250420_100000": {
          "status": "superseded",
          "saved_at": "2025-04-20T10:00:00Z",
          "promoted_at": "2025-04-20T10:05:00Z",
          "metrics": {
            "ndcg@10": 0.0801
          }
        }
      }
    },
    "deepfm": {
      "active_version": "20250421_140000",
      "versions": {
        "20250421_140000": {
          "status": "active",
          "saved_at": "2025-04-21T14:00:00Z",
          "promoted_at": "2025-04-21T14:02:00Z",
          "metrics": {
            "ndcg@10": 0.0915,
            "auc": 0.7234
          }
        },
        "20250419_090000": {
          "status": "rejected",
          "saved_at": "2025-04-19T09:00:00Z",
          "promoted_at": null,
          "metrics": {
            "ndcg@10": 0.0889
          }
        }
      }
    }
  }
}
```

### 版本状态

| 状态 | 说明 |
|------|------|
| `pending` | 刚注册，尚未评测 |
| `active` | 当前生产版本 |
| `superseded` | 曾是生产版本，已被新版本替代 |
| `rejected` | 评测未通过，未提升到生产 |

## 8.3 工作流程

### 训练流程

```
[1] 训练脚本启动
    │
    ▼
[2] 生成版本 ID
    version_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    例如: "20250421_123456"
    │
    ▼
[3] 训练模型，保存到 data/models/{model}/
    model.save() → data/models/item_cf/...
    │
    ▼
[4] 保存版本化副本到 data/model_versions/{model}/{version_id}/
    registry.save_version_artifacts(model_name, version_id)
    │
    ▼
[5] 注册版本到注册表（状态=pending）
    registry.register_version(model_name, version_id, {})
    │
    ▼
[6] 评测模型
    evaluation_metrics = evaluate(model)
    例如: {"ndcg@10": 0.0842, "precision@10": 0.0125}
    │
    ▼
[7] 对比并自动提升
    promoted = registry.compare_and_promote(model_name, version_id, evaluation_metrics)
    │
    ├── 新版本 NDCG@10 > 旧版本 → 提升（status=active）
    │    └── 复制文件到 data/models/{model}/
    │    └── 更新注册表 active_version
    │
    └── 新版本 NDCG@10 ≤ 旧版本 → 拒绝（status=rejected）
         └── 生产目录保持不变
    │
    ▼
[8] 清理旧版本
    registry.cleanup_old_versions(model_name, keep=3)
    └── 删除最老的非 active 版本（保留最近 3 个）
```

### 评测流程

```
[1] 管理员选择评测目标
    ├── 全部生产模型
    ├── Funnel（多路召回管线）
    ├── 特定模型的所有版本
    └── 特定模型的特定版本
    │
    ▼
[2] 启动评测任务
    POST /admin/training/evaluate
    ?model=item_cf
    &version_dir=/app/data/model_versions/item_cf/20250421_123456
    │
    ▼
[3] 评测脚本运行
    → 指定版本目录加载模型
    → 运行评测
    → 生成评测报告
    │
    ▼
[4] 保存结果
    → data/evaluation_progress/{task_id}.json（进度）
    → data/evaluation_progress/{task_id}_report.json（结果）
    │
    ▼
[5] 前端显示
    → SSE 实时进度
    → LogDialog 显示评测结果表格
```

## 8.4 核心代码

### ModelRegistry 类

`ml_pipeline/models/versioning.py`

主要方法：

| 方法 | 说明 |
|------|------|
| `load()` | 加载注册表 |
| `save(data)` | 保存注册表（原子写） |
| `save_version_artifacts(model, version_id)` | 复制生产模型到版本目录 |
| `register_version(model, version_id, metrics)` | 注册新版本 |
| `compare_and_promote(model, version_id, metrics)` | 对比指标并自动提升 |
| `promote_version(model, version_id)` | 手动提升指定版本 |
| `cleanup_old_versions(model, keep)` | 清理旧版本 |
| `get_active_version(model)` | 获取当前生产版本 |
| `list_versions(model)` | 列出所有版本 |
| `get_all_model_info()` | 获取完整模型信息 |

### 训练脚本集成

```python
# ml_pipeline/training/train_itemcf.py
from ml_pipeline.models.versioning import ModelRegistry
from ml_pipeline.evaluation.evaluate_trained import evaluate_item_cf

registry = ModelRegistry()

# [1] 生成版本 ID
version_id = datetime.now().strftime("%Y%m%d_%H%M%S")

# [2] 训练并保存到生产目录
train_item_cf_model()
# 模型保存在 data/models/item_cf/

# [3] 保存版本副本
registry.save_version_artifacts("item_cf", version_id)

# [4] 注册版本
registry.register_version("item_cf", version_id, {})

# [5] 评测
metrics = evaluate_item_cf()
# {"ndcg@10": 0.0842, "precision@10": 0.0125, ...}

# [6] 自动提升
promoted = registry.compare_and_promote("item_cf", version_id, metrics)
if promoted:
    logger.info("New model promoted to production (NDCG@10 improved)")
else:
    logger.info("New model rejected (NDCG@10 did not improve)")
```

### 每版本评测

```bash
# 评测特定版本
uv run python -m ml_pipeline.evaluation.evaluate_trained \
  --model item_cf \
  --version-dir /app/data/model_versions/item_cf/20250421_123456 \
  --task-id eval_version_20250421_123456
```

## 8.5 Admin API

### 模型版本端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/training/model-versions` | 获取所有模型版本信息 |
| GET | `/admin/training/model-versions/{model}` | 获取特定模型的版本列表 |
| POST | `/admin/training/model-versions/{model}/{version_id}/promote` | 手动提升指定版本 |
| GET | `/admin/training/eval-history` | 获取评测历史列表 |
| GET | `/admin/training/eval-report/{task_id}` | 获取特定评测报告 |

### 响应示例

```json
// GET /admin/training/model-versions
{
  "primary_metric": "ndcg@10",
  "keep_versions": 3,
  "models": {
    "item_cf": {
      "active_version": "20250421_123456",
      "versions": {
        "20250421_123456": {
          "status": "active",
          "saved_at": "2025-04-21T12:34:56Z",
          "promoted_at": "2025-04-21T12:35:00Z",
          "metrics": {
            "ndcg@10": 0.0842,
            "precision@10": 0.0125
          }
        }
      }
    }
  }
}
```

## 8.6 前端展示

### Models.vue 组件

- **模型可用性网格**：显示各模型状态和参数
- **评测指标对比**：表格对比不同版本的评测指标
- **版本历史列表**：显示所有版本，支持手动提升
- **每版本评测下拉**：选择特定版本进行评测

```
┌─────────────────────────────────────────────────────────────┐
│ 模型状态                                    [全部] [ItemCF]  │
├─────────────────────────────────────────────────────────────┤
│ ● ItemCF    [可用]  参数: embedding_dim=64                  │
│ ○ SVD       [未训练]                                        │
│ ● DeepFM    [可用]  参数: hidden_dims=[256,128,64]          │
│ ○ SASRec    [未训练]                                        │
├─────────────────────────────────────────────────────────────┤
│ 评测指标对比                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 版本          │ NDCG@10 │ Precision@10 │ Recall@10      │ │
│ │ ItemCF/最新   │ 0.0842  │ 0.0125       │ 0.0456         │ │
│ │ DeepFM/最新   │ 0.0915  │ 0.0138       │ 0.0489         │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 版本历史                                                     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ItemCF                                                  │ │
│ │  20250421_123456  [Active]  NDCG@10: 0.0842  [提升]    │ │
│ │  20250420_100000  [Superseded]  NDCG@10: 0.0801         │ │
│ │  20250419_090000  [Rejected]  NDCG@10: 0.0789          │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 8.7 推理加载

推理代码**始终**从 `data/models/{model}/` 加载模型，不受版本系统影响：

```python
# ml_pipeline/inference/recall.py
def _get_item_cf():
    model_dir = "/app/data/models/item_cf"  # 固定路径
    meta_path = os.path.join(model_dir, "meta.json")
    # 加载模型...
```

版本提升时自动更新此目录，推理代码无需修改。
