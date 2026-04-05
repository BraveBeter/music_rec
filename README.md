<div align="center">
  <h1>🎵 个性化音乐推荐系统 (Music Recommendation System)</h1>
  <p>一个包含完整推荐链路、多级容灾降级的工业级个性化音乐推荐引擎</p>

  <p>
    <img src="https://img.shields.io/badge/Frontend-Vue%203%20%7C%20Vite-42b883?style=flat-square&logo=vuedotjs" alt="Vue 3">
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/Database-MySQL%20%7C%20Redis-4479A1?style=flat-square&logo=mysql" alt="DB">
    <img src="https://img.shields.io/badge/AI-SASRec%20%7C%20DeepFM-EE4C2C?style=flat-square&logo=pytorch" alt="AI">
  </p>
</div>

---

## 📖 项目简介

真正的工业级推荐架构并非简单调用一个深度学习黑盒算法，而是囊括**“提召排”（提取、召回、排序）**和降级防抖的高可用系统。

本项目利用 `FastAPI` (原生异步机制) 搭配 `Vue 3` 构建强交互前台，并融合了从 **流行度冷启动**、**离线托底** 到 **多路召回 (ItemCF + SASRec)** 与 **深度模型张量排序 (DeepFM / ONNX)** 的全栈式混合推荐管线。在保证代码高内聚低耦合的基础上极大地拔高了服务吞吐阈值。

## ✨ 核心特性

- **🚀 异步极速流转**：摒弃传统同步框架。系统连接池基于 `aiomysql`，全面解耦 I/O 阻塞；借助 Redis 的 `LPUSH`，达到单次毫秒级听歌历史流水构建。
- **🧠 现代“双曲塔”推理引擎**：纯源生整合了 `ItemCF`（协同过滤）、`SASRec`（自注意力历史特征序列表达）与 `DeepFM`（深层神经元特征切面网络），精确捕获用户“显性”和“隐形”的兴趣意图。
- **🛡️ 坚不可摧的降级分流架构 (Fallback)**：推荐中枢设有多达 L1-L4 的防断层护城河：Redis 短期缓存缓冲 $\rightarrow$ ML 双路推演 $\rightarrow$ 离线 SQL 兜底 $\rightarrow$ 全球热榜强制冷启动。不管并发灾难多严重，你的系统永不报 404！
- **👥 真实的合成沙盒支持**：搭载了 `generate_synthetic_data` 矩阵算法合成机。不需你辛苦埋点，系统自动化利用伪高斯生成 60 位具象化偏好的听众并播下 300,000+ 的测试数据记录用以练就原始神经模型。

---

## 🛠️ 技术底座全景

| 模块区域 | 主力选型 | 组件 & 库 | 职能定义 |
| :---: | :---: | :---: | :--- |
| **前端呈现** | `Vue 3` | `Vite` \ `Pinia` \ `vue-router` \ `Axios` | 抛却被重装系统与繁重编译捆绑的生态，基于 CompositionAPI 高速渲染，利用无死锁的双态阻断 Axios 锁消除 401 轮回攻击。 |
| **后端枢纽** | `Python` | `FastAPI` \ `SQLAlchemy` \ `PyJWT` | 事件驱动级请求代理中枢。将 JWT 解密拦截做成最干净轻便的 Depends 依赖漏斗。 |
| **调度与持久**| `引擎` | `MySQL 8.0` \ `Redis 7.0` | 一手建立高并发读写双向缓冲管道。通过 MySQL 保存特征关联与表关系，Redis 完成极速毫秒级动作序列缓存。 |
| **核心算法** | `AI 矩阵` | `Sklearn` \ `PyTorch` \ `Numpy`  | 基于张量拼接的深排执行厂，脱手任何第三方臃肿推荐商服务，直达硬件深层算力。 |

---

## ⚡ 极速启动 (Quick Start)

**前期准备**：请确保你的机器安装了 **Git**, 和 **Docker Engine + Docker Compose**。本系统所有微服务环境（包含数据库）全部实现容器隔离化，宿主机无需装载沉重的本地包依赖。

### 1. 抓取与环境置空
如果你拉取了这套库，不论这是新老宿主机。**首先要拉取，然后确保历史的交叉污染卷、脏容器被物理终结（此步极其重要）：**

```bash
git clone https://gitee.com/BraveBeter/music_rec.git
cd music_rec

# 清空可能残留的无主污染映射字典
docker-compose down -v --remove-orphans
```

### 2. 唤醒宇宙矩阵并行构建
直接进入部署阶段，将这 5 组包含前后端+双库+任务机群组统一点火：

```bash
docker-compose up -d --build
```
> *Tips：此命令将向宿主开放 13307 (MySQL), 16379 (Redis), 13000 (前端) 隔离防冲突通道，请确保本地防火墙与占用释放了它们。*

### 3. 数据播种与观星
项目正在拉取 Deezer 全球热门公域数据并打标假数据特性图网。不要急于测试接口，通过日志注视过程：

```bash
docker logs musicrec_seeder -f
```
当日志弹框出现最终标志 `✅ Generated 60 users, xxx interactions` 时即代表特征数据库建立并播种完毕。

此时，立刻切入浏览器访问网关点：**`http://127.0.0.1:13000`** 体验工业级推送魔力。

---

## 📚 巨细无遗的“白盒”解构手册
想深入读懂每一层推荐是怎么利用余弦公式跑出 0.9 倍率得分的？想把 FastAPI 和 Redis 的高频管线原样搬运到自己的新公司项目中？我们准备了一篇多达数千字，精确到文件每个字面量和字节参数的顶级重现级文档，将系统的防逆向与死锁解毒避雷思路全盘托出：

👉 **[前往 `docs/System_Documentation_Reproduction_Level.md` 翻阅这本绝对硬核手册](./docs/System_Documentation_Reproduction_Level.md)**

---
> *本项目基于前沿工业界推荐落地场景搭建开发，适用于学习、毕业论证与小微工业化起步实践。由开发者 Antigravity AI 结对协助保障稳固代码执行体。*
