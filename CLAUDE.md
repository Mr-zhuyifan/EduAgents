# CLAUDE.md

本文件为 Claude Code 在本仓库工作时的引导说明。

## 项目是什么

EduAgent —— 面向 IT 教培机构的 AI 多智能体教学辅助平台。四个独立 Agent（智能问答 QA / 试卷批改 Exam / 简历审查 Resume / 模拟面试 Interview）跑在 FastAPI + LangGraph 之上，上层有 Orchestrator 编排层。

**只看后端。** `frontend/` 目录是 Vue3 前端，除非任务明确要求，不要读取或修改。

详细的架构与交接说明见 `docs/`：
- `docs/项目交接文档.md` —— 全局交接文档（**接手先读这个**）
- `docs/agent-interview.md` —— 模拟面试 Agent 详解
- `docs/agent-qa.md` / `docs/agent-exam.md` / `docs/agent-resume.md` —— 另外三个 Agent 详解

## 常用命令

```bash
# 启动后端（必须在项目根目录执行，因为模块路径是 backend.xxx）
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 单独编译某个 Agent 的图并打印节点（部分 graph.py 带 __main__）
python -m backend.agents.interview.graph
python -m backend.agents.qa.graph

# 基础设施（先配好 .env）
docker-compose --env-file .env up -d postgres redis minio etcd milvus langfuse

# 初始化数据
python scripts/_01_init_milvus.py        # 建 Milvus Collection
python scripts/_04_seed_data.py          # 灌测试数据
python scripts/_05_seed_standard_exam.py # 标准试卷

# 知识库导入
python scripts/_02_build_knowledge_base.py --file <路径> --course_id <课程UUID>

# 接口文档
open http://localhost:8000/docs
```

> `scripts/` 下的脚本带 `_01_` 之类前缀是为了控制执行顺序，不是私有模块。注意 `scripts/init_db.sql` 是一个**目录**（空），真正的建表 SQL 是 `scripts/_03_init_db.sql`。

## 环境注意事项

- **本机实际使用 Python 3.13.5**（`.venv/lib/python3.13`），而 `README.md` 写的是「Python 3.11 严格锁定」，`requirements.txt` 也按 3.11 锁的版本 —— 以实际能跑起来的环境为准，改动依赖前先确认。
- **`config.py` 读取的是项目根目录的 `.env`**，不是 README 里说的 `.env.local`（`backend/config.py:10`）。`extra = "ignore"`，多余字段不会报错。
- 三个本地模型（BGE-M3 / BGE-Reranker / MiniLM）都是**进程内调用**，启动时由 `lifespan` 并行预热（`backend/main.py:47-62`）。权重在 `models/`，已被 `.gitignore` 忽略，首次运行需自行下载；`BGEReranker` 在本地目录缺失时会回退到 HuggingFace 的 `BAAI/bge-reranker-v2-m3`。
- 所有端口都从 `.env` 读，**禁止硬编码**。宿主机端口已整体偏移避让：PG 5433 / Redis 6380 / MinIO 9002、9003 / Milvus 19531。

## 代码约定（改代码时请遵守）

1. **模型只能通过 `backend/core/llm_factory.py` 获取**，禁止直接 `init_chat_model`。
   - 普通模型：`get_llm(agent_type, temperature=..., streaming=...)`
   - 结构化输出：`get_structured_llm(agent_type, SomePydanticModel)`
   - 可用的 `agent_type` 定义在 `_AGENT_MODEL_ROUTING`（`llm_factory.py:32-40`），未知类型会 `raise ValueError`。要换模型只改这张表。
   - 模型名有二次映射：`_MODEL_ID_MAP`（`llm_factory.py:43-46`）。
2. **每个 Agent 统一四文件结构**：`state.py`（State + Pydantic 模型）/ `graph.py`（图组装）/ `nodes.py`（业务逻辑）/ `prompts.py`（提示词常量）。新增 Agent 请照此布局。
3. **Prompt 一律放 `prompts.py`**，用模块级常量，不要在 `nodes.py` 里内联长提示词。现有写法混用 dict（`TECH_BASE_PROMPT["followup"]`）与纯字符串，跟随所在文件即可。
4. **Checkpointer 必须按 Agent 隔离**：`get_memory_saver("interview")` 等。不同 Agent 的 State schema 不同，共用同一个 `MemorySaver` 会导致 msgpack 序列化冲突（`backend/core/memory.py:11-14` 有注释说明）。
5. **会话 thread_id 统一用 `build_thread_id(student_id, session_id)`**，调用配置用 `build_config(...)`。
6. **API 层放 `backend/api/v1/`**，并在 `backend/api/router.py` 注册（带 prefix 与 tags）。所有业务路由挂在 `/api/v1` 下（`main.py:98`）。
7. **鉴权用依赖注入** `Depends(get_current_user)`，返回 `{"user_id", "role", "tenant_id"}`。DB 用 `AsyncSessionLocal`，全异步。
8. **数据库改表必须走幂等迁移**：在 `backend/db/migrations.py` 的 `_MIGRATIONS` 列表追加 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 这类语句。禁止写 `DROP` / `TRUNCATE`。同步在 `scripts/_03_init_db.sql` 补上字段定义。
9. **所有外部依赖调用都要兜底**。这是本项目的硬性风格：LLM 失败、DB 失败、MCP 失败一律记 warning 日志后走降级，**不向上抛异常**，保证用户始终能拿到响应。
10. **日志用 `get_logger(__name__)`**，结构化写法 `logger.info("event.name", key=value)`，不要用 print。
11. 注释与文档全部用中文，风格是「每行关键代码上一个短注释」—— 保留这个风格。

## 架构速览

```
frontend (Vue3 :3000)
      │ HTTP / SSE
backend/main.py (FastAPI :8000)
      │  /api/v1/{auth,chat,qa,exam,resume,interview}
      ├── core/orchestrator.py   编排层（AgentRequest → AgentResponse；含 pipeline）
      ├── core/llm_factory.py    LLM 统一入口
      ├── core/memory.py         MemorySaver / thread_id / 滑窗 / 摘要压缩
      ├── core/retry.py          with_retry 装饰器（三层兜底）
      ├── core/knowledge_base.py BGE-M3 双输出 + Milvus 混合检索
      ├── core/reranker.py       BGE-Reranker 精排
      ├── core/query_classifier.py MiniLM 二分类（QA 内部用）
      ├── agents/{qa,exam,resume,interview}/  四个 LangGraph
      └── mcp/                   知识库 MCP + 联网搜索 MCP
数据层：PostgreSQL · Redis · Milvus · MinIO
```

四个 Agent 的图拓扑（细节见 `docs/`）：

| Agent | 拓扑 | 特点 |
|-------|------|------|
| QA | 10 节点 + 3 组条件边 | 意图分类 → 多策略检索 → 生成；有流式 |
| Exam | 9 节点**线性链** | 三轨并行批改 + `interrupt()` 实现 HitL 教师确认 |
| Resume | 8 节点**直线** | 六维度并行评分，无 checkpointer（一次性任务） |
| Interview | 7 节点 + 1 条件边 | 五阶段状态机，跨轮有状态，依赖 MemorySaver |

## 已知的坑（改动相关代码前必看）

完整的清单在 `docs/项目交接文档.md` 的「已知问题」章节，这里只列最容易踩的：

- **`MemorySaver` 是进程内内存**，后端一重启所有会话历史丢失。多 worker 部署下 HitL 的 `confirm` 会路由不到持有 checkpoint 的进程。生产要换 `AsyncPostgresSaver`。
- **面试 SSE 可能不是真流式**：`generate_response` 里的 `get_llm` 没传 `streaming=True`，`astream_events` 可能只产出一个完整 chunk。QA 的生成节点传了 `streaming=True`，可作对照。
- **QA 的长期记忆完全失效（两个 bug 叠加，比想象的严重）**：
  ① `agents/qa/nodes.py:806` 的 UPSERT 被缩进到了 `if state.get("should_summarize", False):` 块内部（该 `if` 在 `:793`，是 4 空格）；
  ② `should_trigger_summary` 在生成节点求值时，`messages` **已含本轮 HumanMessage、尚未含本轮 AI 回复**（`qa.py:58` 先塞进 initial_state 才 invoke），故 `dialogue_count = 2N-1` 恒为奇数，`dialogue_count % 20 == 0` **永不成立**。
  两者叠加 → `should_summarize` 恒 False → **`qa_sessions` 表永远没有 QA 写入的行**（不是「第 10/20/30 轮才落库」，那是我早期文档的错误说法）。面试 Agent 的 `should_summarize`（`agents/interview/nodes.py:520`）有同样的奇数缺陷，但它的 UPSERT 缩进正确、每轮都写，所以表现为「行在、`summary` 列恒为 NULL」。
- **`fallback_used` 是死字段**：四个 Agent 的 State 都声明了它，但全仓库**唯一的写入点是 `resume/nodes.py:432`，且硬编码 `False`**（不是判断结果）→ 任何 Agent 中都恒为 `False`，降级状态无法上报给前端。
- **Exam 的 Judge0 沙箱执行未实现**，代码题完全靠 LLM 静态阅读（README 提到 Judge0 是与实现不符的）。
- **Resume 的 MinIO 上传/下载未实现**，PDF 走本地 `tempfile`；`upload_to_minio_node` / `download_pdf_node` 是空跑节点。
- **README 说的「MiniLM 意图识别」已不是现状**：跨 Agent 路由现在由 `api/v1/unified_chat.py` 的 LLM 完成（`get_llm("intent")`，6 标签）；MiniLM 只用于 QA 内部 general/specialized 二分类。
- **`tests/` 目录不存在**（README 声称 76 passed）。现有验证方式是 `backend/api/v1/verify_*_e2e.py` 与 `scripts/manual_tests/`。

## 改动风格

- 修 bug 时优先保持最小改动，不要顺手重构无关代码。
- 新增 State 字段时，记得三处同步：`state.py` 定义、`api/v1/*.py` 的 `initial_state`（首轮必须传全量——MemorySaver 里还没有存档）、以及该字段的写入节点。
- 不要提交 `__pycache__`、`.env`、`models/`（当前工作区已有一批 `__pycache__` 被 `git add` 进了暂存区，提交前建议先 `git reset` 掉）。
