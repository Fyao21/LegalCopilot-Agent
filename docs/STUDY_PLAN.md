# 律镜 Legal Copilot Agent 学习顺序与执行计划

## 1. 这份文档怎么用

这份文档只解决一个问题：**应该按照什么顺序学习本项目，才能既看懂代码，又能在求职面试中讲清楚。**

不要从头到尾随机翻阅所有 Markdown，也不要一开始就逐行阅读代码。推荐使用下面的循环：

```text
先知道功能解决什么问题
  → 在页面或接口中亲自运行一次
  → 顺着入口阅读代码
  → 阅读对应测试
  → 用自己的话复述设计
  → 再进入下一个功能
```

建议每天学习 1～2 小时。完整路线约 15 天；如果时间有限，可以使用第 9 节的“7 份文档最短路线”。

---

## 2. 文档总顺序

请严格按照下面的顺序开始：

| 顺序 | 文档 | 主要回答的问题 | 阅读方式 |
|---|---|---|---|
| 1 | [README](../README.md) | 这是什么项目、能做什么、怎么启动 | 先通读，暂时跳过细节 |
| 2 | [产品说明](../PRODUCT_SPEC.md) | 用户是谁、产品流程是什么、当前支持什么 | 理解业务，不看代码 |
| 3 | [项目目标](../PROJECT_GOALS.md) | 项目如何从第一周逐步建设到第八周 | 先看总目标，再按周阅读 |
| 4 | [配置文档](CONFIGURATION.md) | DeepSeek、Embedding、数据库和离线模式如何配置 | 对照自己的 `.env` |
| 5 | [自测手册](../SELF_TEST.md) | 如何证明环境和功能真的正常 | 先完成自动自测和页面验收 |
| 6 | [学习日志](LEARNING_JOURNAL.md) | 每个功能为什么这样设计、数据怎样流动 | 按周阅读，不要一次读完 |
| 7 | [详细接口文档](API_GUIDE_DETAILED.md) | 每个接口的含义、参数和返回结果 | 结合 Swagger/Apifox 操作 |
| 8 | [数据库说明](../db.md) | SQLite、JSONL、测试库和业务表分别保存什么 | 打开 PyCharm Database 对照 |
| 9 | [技术决策记录](decisions/README.md) | 为什么选择 SQLite、LangGraph、离线回退等方案 | 学会解释技术取舍 |
| 10 | [未来优化计划](FUTURE_OPTIMIZATION_PLAN.md) | 当前限制和后续生产化方向 | 不需要背实现细节 |
| 11 | [求职材料](JOB_MATERIALS.md) | 简历和项目介绍应该怎么表达 | 完成代码学习后再看 |
| 12 | [Agent 面试手册](AGENT_INTERVIEW_GUIDE.md) | 面试官可能如何追问 | 先自己回答，再看参考答案 |
| 13 | [演示脚本](DEMO_SCRIPT.md) | 如何在 2～3 分钟内演示项目 | 最后练习 |

其中第 1～6 份是基础必读，第 7～10 份用于深入理解，第 11～13 份用于求职准备。

---

## 3. 第一阶段：先理解并跑通项目

### 第 1 步：阅读 README

阅读：

- [README](../README.md)

重点关注：

1. 项目解决的法律 Agent 问题；
2. 前端、FastAPI、LangGraph、SQLite、Embedding 的关系；
3. 离线可靠和智能 Agent 两种模式；
4. 快速启动命令；
5. 当前已经完成的核心能力。

本步骤暂时不要研究每个类和函数。

完成标准：

- 能用 3 句话说明项目用途；
- 能画出“前端 → API → Agent 工作流 → 检索 → 报告”的大致流程；
- 知道离线模式不需要真实模型 Key。

### 第 2 步：理解产品流程

阅读：

- [产品说明](../PRODUCT_SPEC.md)

重点回答：

1. 用户输入什么？
2. 系统输出什么？
3. 为什么不能让大模型直接生成法律结论？
4. 为什么需要引用审核、用户追问和人工审批？
5. 当前明确不支持哪些生产能力？

完成标准：

- 能从用户角度复述一次完整案件分析流程；
- 能区分“功能已经完成”和“未来计划支持”；
- 能说明项目是技术教学与求职演示，不构成法律意见。

### 第 3 步：运行项目

依次阅读：

1. [README 的快速启动部分](../README.md)；
2. [配置文档](CONFIGURATION.md)；
3. [自测手册](../SELF_TEST.md)。

建议实际执行：

```powershell
# 项目根目录
.\.venv\Scripts\python.exe scripts\run_self_test.py

# 后端
.\.venv\Scripts\python.exe -m app.main

# 前端
cd frontend
pnpm run dev
```

然后打开：

- 后端接口文档：`http://127.0.0.1:8000/docs`
- 前端页面：`http://127.0.0.1:5173`

至少完成一次离线案件分析，不要先依赖 LLM。

完成标准：

- `/health` 返回正常；
- Swagger 页面能打开；
- 前端能提交案件并看到运行轨迹；
- 自动测试全部通过；
- 知道 `.env` 与 `.env.example` 的区别。

---

## 4. 第二阶段：按周学习功能和代码

从这里开始，按“学习日志 → 代码 → 测试 → 手工操作”的顺序学习。不要直接从第七周倒着读。

### 第 4 步：第一周——后端与检索基线

先读：

- [项目目标中的第一周](../PROJECT_GOALS.md)
- [学习日志中的第一周](LEARNING_JOURNAL.md)

再看代码：

1. `app/main.py`：找到 `/health`、法规搜索和同步案件接口；
2. `app/schemas.py`：理解请求与响应 Schema；
3. `app/models.py`：理解 SQLAlchemy 表模型；
4. `app/database.py`：理解数据库会话；
5. `app/services/seed.py`：理解启动数据；
6. `app/services/case_analyzer.py`：理解规则分析基线；
7. `app/services/mixed_retriever.py`：理解最初的混合检索。

最后看：

- `tests/test_api.py`
- `tests/test_services.py`

需要掌握：

- FastAPI 路由、依赖注入和 Pydantic 校验；
- SQLite 为什么适合第一阶段；
- 规则分析为什么可以作为可靠基线；
- 关键词分数与哈希向量分数如何组合。

验收问题：

> 用户提交一个问题以后，请从 `app/main.py` 开始，说出数据经过哪些函数和数据表。

### 第 5 步：第二周——真实 RAG 与 Agent 工作流

先读：

- [项目目标中的第二周](../PROJECT_GOALS.md)
- [学习日志中的第二周及相关故障修复记录](LEARNING_JOURNAL.md)

再看代码：

1. `app/llm/client.py`：模型请求和结构化输出；
2. `app/services/embedding_provider.py`：真实 Embedding 与哈希回退；
3. `app/services/retrieval_service.py`：检索 provider 选择；
4. `app/services/citation_reviewer.py`：引用真实性审核；
5. `app/services/report_writer.py`：结构化报告；
6. `app/workflows/legal_report_graph.py`：LangGraph 节点和状态流转。

最后看：

- `tests/test_second_week.py`
- `tests/test_services.py` 中的 LLM、Embedding 和回退测试

需要掌握：

- RAG 与普通大模型问答的区别；
- Chat 模型和 Embedding 模型不是同一个配置；
- LangGraph State、Node、Edge 的含义；
- 为什么模型失败后要透明降级，而不是假装仍然调用了模型；
- 为什么引用必须回查数据库。

验收问题：

> 智能 Agent 模式为什么仍然可能显示 `provider=hash`？这是否代表 Chat 模型也没有运行？

### 第 6 步：第三周——前端、后台任务与报告导出

先读：

- [项目目标中的第三周](../PROJECT_GOALS.md)
- [自测手册中的第三周验收](../SELF_TEST.md)
- [学习日志中的第三周](LEARNING_JOURNAL.md)

再看代码：

1. `frontend/src/App.tsx`：案件分析主页面；
2. `frontend/src/api.ts`：前端请求封装；
3. `frontend/src/types.ts`：TypeScript 数据结构；
4. `frontend/src/styles.css`：页面布局和状态样式；
5. `app/main.py` 中 `/api/v1/runs`、任务查询与导出接口；
6. `app/tasks.py`：后台任务。

最后看：

- `tests/test_third_week.py`

需要掌握：

- 为什么耗时 Agent 使用任务 ID 和轮询；
- 前端如何把后端节点状态展示为运行轨迹；
- Markdown/PDF 报告如何生成和下载；
- 文件类型、大小和 MIME 校验为什么必须放在后端。

验收问题：

> 为什么创建 Agent 任务返回 202，而不是等报告生成完成后直接返回 200？

### 第 7 步：第四周——评测与工程质量

先读：

- [项目目标中的第四周](../PROJECT_GOALS.md)
- [README 的评测与测试部分](../README.md)
- [学习日志中的第四周](LEARNING_JOURNAL.md)

再看：

1. `eval/`：评测数据和指标计算；
2. `eval/results/latest.md`：最近一次评测结果；
3. `.github/workflows/`：CI 流程；
4. `pyproject.toml`：Ruff、mypy 和测试配置；
5. `scripts/run_self_test.py`：统一自测入口。

需要掌握：

- Recall@K、MRR、案件类型准确率的含义；
- 为什么小型教学集的高分不能外推到生产效果；
- 为什么 CI 必须强制离线，不能消耗真实 API Key；
- 单元测试、接口测试、评测和浏览器验收的区别。

验收问题：

> 测试全部通过，为什么仍然不能证明法律回答一定正确？

### 第 8 步：第五周——可恢复的多轮追问

先读：

- [项目目标中的第五周](../PROJECT_GOALS.md)
- [学习日志中的第五周](LEARNING_JOURNAL.md)
- [求职材料中的第五周亮点](JOB_MATERIALS.md)

再看代码：

1. `app/workflows/legal_report_graph.py` 中 `clarify_user`；
2. `app/models.py` 中待办、回答与状态版本字段；
3. `app/main.py` 中 pending-action 和 clarifications 接口；
4. `tests/test_fifth_week.py`。

需要掌握：

- 信息不足时为什么应暂停，而不是让模型猜测；
- LangGraph `interrupt` 和 `Command(resume)`；
- checkpoint 如何在服务重启后恢复；
- 幂等键和乐观锁分别解决什么问题；
- 为什么要限制追问轮次。

验收问题：

> 如果用户重复提交同一个追问答案，系统怎样避免 Agent 恢复两次？

### 第 9 步：第六周——人工审批与报告版本

先读：

- [项目目标中的第六周](../PROJECT_GOALS.md)
- [学习日志中的第六周](LEARNING_JOURNAL.md)
- [ADR 0007](decisions/0007-require-approval-before-report-release.md)
- [求职材料中的第六周亮点](JOB_MATERIALS.md)

再看代码：

1. `app/models.py` 中 `report_versions` 和 `agent_approvals`；
2. `app/workflows/legal_report_graph.py` 中审批与修改节点；
3. `app/main.py` 中审批、版本和导出接口；
4. 前端审批卡片与版本列表；
5. `tests/test_sixth_week.py`。

需要掌握：

- 为什么模型生成的报告只能先成为草稿；
- 批准、要求修改、驳回三条状态路径；
- 为什么版本正文使用追加式存储；
- 为什么审批之后才允许导出；
- 并发审批中的幂等与乐观锁。

验收问题：

> 如何证明“未批准不能下载”是后端约束，而不是前端隐藏了按钮？

### 第 10 步：第七周——法规时效与版本证据链

先读：

- [项目目标中的第七周](../PROJECT_GOALS.md)
- [学习日志末尾的第七周记录](LEARNING_JOURNAL.md)
- [ADR 0008](decisions/0008-filter-law-versions-before-retrieval.md)
- [求职材料中的第七周亮点](JOB_MATERIALS.md)

再看代码：

1. `app/models.py` 中 `Law` 和 `LawVersion`；
2. `app/services/law_versioning.py`；
3. `app/services/mixed_retriever.py` 中日期过滤；
4. `app/services/citation_reviewer.py` 中版本校验；
5. `app/services/report_writer.py` 中版本展示；
6. 前端案件日期、效力标签和引用详情；
7. `tests/test_seventh_week.py`。

需要掌握：

- 法规实体和法规版本为什么拆表；
- `[effective_from, effective_to)` 半开区间；
- `repealed` 为什么仍可能在历史时点适用；
- 为什么必须先按日期过滤，再做 Top-K；
- `article_id + law_version_id` 如何形成证据链。

验收问题：

> 为什么相同合同问题在 2020-12-31 和 2021-01-01 会返回不同法规？

### 第 11 步：第八周——Agent Trace、指标与费用

先读：

- [项目目标中的第八周](../PROJECT_GOALS.md)
- [学习日志末尾的第八周记录](LEARNING_JOURNAL.md)
- [ADR 0009](decisions/0009-store-allowlisted-agent-spans.md)
- [求职材料中的第八周亮点](JOB_MATERIALS.md)

再看代码：

1. `app/services/observability.py` 的 OpenTelemetry、allowlist 与费用计算；
2. `app/workflows/legal_report_graph.py` 的节点、Chat、Embedding 和恢复 Span；
3. `app/models.py` 的 `AgentRunSpan` 与运行聚合字段；
4. `app/services/monitoring.py` 的单次链路、平均与 P95；
5. `app/main.py` 的 Trace 关联和两个监控接口；
6. `frontend/src/MonitoringPage.tsx`；
7. `tests/test_eighth_week.py`。

需要掌握：

- Trace、Span、父子关系分别是什么；
- 为什么 HTTP 创建请求和后台 Agent 要共享 Trace ID；
- 平均耗时与 P95 的区别；
- Token 估算费用为什么不等于服务商账单；
- 为什么遥测只能使用 allowlist；
- 离线模式显示 0 Token/费用为什么更可信。

验收问题：

> 如果用户说“这次 Agent 很慢而且好像没用模型”，你怎样只用监控页定位慢点、实际 provider、重试和降级原因？

---

## 5. 第三阶段：专题学习接口、数据库与架构

### 第 12 步：按业务流程学习接口

阅读：

- [详细接口文档](API_GUIDE_DETAILED.md)
- [简明接口参考](API_REFERENCE.md)
- `docs/openapi.json`

不要按照 URL 字母顺序学习，而要按照用户流程：

```text
GET /health
  → 获取随机问题示例
  → 搜索法规
  → 创建 Agent 任务
  → 查询任务状态
  → 读取待处理动作
  → 回答追问
  → 查看引用和草稿
  → 审批或要求修改
  → 查看单次 Trace 与监控概览
  → 下载最终报告
  → 录入或批量导入法规
```

每学一个接口都要回答：

1. 谁会调用它？
2. 请求参数为什么这样设计？
3. 正常响应是什么？
4. 可能返回哪些错误？
5. 它会写入哪些表？
6. 是否需要幂等或并发保护？

完成标准：

- 能在 Swagger 或 Apifox 独立跑通一条 Agent 流程；
- 能解释 200、201、202、409、415、422、503 在本项目中的典型场景。

### 第 13 步：学习数据库

阅读：

- [数据库说明](../db.md)
- `app/models.py`
- `app/migrations.py`

使用 PyCharm Database 对照查看：

- `legal_articles`
- `laws`
- `law_versions`
- `article_embeddings`
- `agent_runs`
- `agent_run_steps`
- `agent_run_citations`
- `report_versions`
- `agent_approvals`

需要重点区分：

- `data/sample_laws.jsonl`：启动种子数据，不是数据库；
- `data/legal_copilot.db`：日常运行数据库；
- `data/test_legal_copilot.db`：自动测试数据库；
- LangGraph checkpoint：恢复执行位置；
- 业务表：查询、展示、审计和版本记录。

完成标准：

- 能说明一条法规、一次 Agent 运行、一条引用和一个报告版本分别存在哪里；
- 能说明为什么不能把 checkpoint 当成完整业务数据库。

### 第 14 步：阅读技术决策

按编号阅读：

1. [ADR 0001：先使用 SQLite](decisions/0001-use-sqlite-first.md)
2. [ADR 0002：保留离线模式](decisions/0002-keep-offline-mode.md)
3. [ADR 0003：审核引用](decisions/0003-review-citations.md)
4. [ADR 0004：使用 LangGraph](decisions/0004-use-langgraph.md)
5. [ADR 0005：未来迁移 PostgreSQL/pgvector](decisions/0005-migrate-to-postgresql-pgvector.md)
6. [ADR 0006：不暴露 Chain-of-Thought](decisions/0006-no-chain-of-thought.md)
7. [ADR 0007：报告发布前必须审批](decisions/0007-require-approval-before-report-release.md)
8. [ADR 0008：召回前过滤法规版本](decisions/0008-filter-law-versions-before-retrieval.md)

阅读 ADR 时不要只记结论，要找出：

- 当时遇到的业务问题；
- 可选方案；
- 为什么选择当前方案；
- 方案带来的代价；
- 未来什么时候需要替换。

完成标准：

- 能用“背景—选择—原因—代价”解释至少 4 个技术决策；
- 面试时不会把 SQLite、规则回退说成永远最优方案。

---

## 6. 第四阶段：求职与面试准备

### 第 15 步：先自己讲，再看参考答案

先关闭文档，用自己的话回答：

1. 请介绍一下这个项目；
2. 为什么要使用 Agent，而不是普通 RAG？
3. LangGraph 在项目中解决了什么问题？
4. 模型调用失败以后如何处理？
5. 如何防止模型编造法条？
6. 多轮追问怎样暂停和恢复？
7. 人工审批怎样处理重试与并发？
8. 为什么法规必须按案件日期过滤？
9. 当前项目离生产环境还缺什么？

再阅读：

- [求职材料](JOB_MATERIALS.md)
- [Agent 面试手册](AGENT_INTERVIEW_GUIDE.md)

不要逐字背诵。把参考答案改成自己能自然表达的版本。

完成标准：

- 能完成 30 秒、2 分钟和 5 分钟三个长度的项目介绍；
- 每个核心功能都能说出一个问题、一个方案、一个测试和一个限制；
- 遇到项目未实现的能力时能诚实说明未来方案。

### 第 16 步：练习项目演示

阅读：

- [2～3 分钟演示脚本](DEMO_SCRIPT.md)

建议演示顺序：

1. 说明项目要解决的风险；
2. 输入事实不完整的案件，展示多轮追问；
3. 展示 Agent 节点轨迹；
4. 打开法规引用和版本详情；
5. 展示报告草稿和人工审批；
6. 批准后下载最终报告；
7. 简短展示测试与 CI。

完成标准：

- 3 分钟内完成演示；
- 不展示 `.env`、API Key、个人信息或真实案件材料；
- 页面失败时能切换到离线模式继续演示；
- 能解释页面上的 `rules`、`llm`、`fallback`、`hash` 和法规效力标签。

---

## 7. 建议的 15 天安排

| 天数 | 学习内容 | 当天输出 |
|---|---|---|
| 第 1 天 | README、产品说明 | 写出 3 句话项目介绍 |
| 第 2 天 | 配置、启动、自测 | 独立启动前后端并跑通离线分析 |
| 第 3 天 | 第一周后端、Schema、数据库 | 画出同步案件的数据流 |
| 第 4 天 | 检索、Embedding、引用审核 | 解释关键词、向量和混合检索 |
| 第 5 天 | LangGraph 工作流 | 手画节点图并解释每个节点 |
| 第 6 天 | 前端、后台任务、报告导出 | 从点击按钮追踪到后端接口 |
| 第 7 天 | 评测、测试、CI | 解释测试与评测的区别 |
| 第 8 天 | 第五周多轮追问 | 解释 interrupt、resume、幂等 |
| 第 9 天 | 第六周审批与版本 | 解释审批状态机和版本表 |
| 第 10 天 | 第七周法规时效 | 比较两个日期的检索结果 |
| 第 11 天 | 第八周运行监控 | 用 Trace 定位最慢节点、模型和降级 |
| 第 12 天 | 逐接口文档、Apifox | 手工跑通一条完整接口流程 |
| 第 13 天 | 数据库与 ADR | 讲清 5 个技术决策 |
| 第 14 天 | 求职材料、面试题 | 完成 2 分钟项目介绍 |
| 第 15 天 | 演示脚本、模拟面试 | 完成一次 3 分钟录屏或口述演示 |

如果某一天的完成标准没有达到，不要急着进入下一天。先回到对应测试和代码入口重新走一遍。

---

## 8. 每次阅读代码的固定方法

遇到任何功能，都按照下面的顺序追踪：

```text
前端事件
  → frontend/src/api.ts
  → app/main.py 路由
  → app/schemas.py 参数校验
  → service 或 workflow
  → app/models.py 数据持久化
  → API 响应
  → tests/ 对应测试
```

为每个功能记录一张学习卡片：

```text
功能名称：
解决的问题：
入口接口：
核心文件：
使用的数据表：
正常数据流：
失败与降级：
测试方法：
已知限制：
面试表达：
```

学习的目标不是记住全部代码，而是能找到入口、顺着数据流定位实现，并能解释为什么采用这个方案。

---

## 9. 时间不足时的最短路线

如果只有 2～3 天，只读下面 7 份文档：

1. [README](../README.md)
2. [产品说明](../PRODUCT_SPEC.md)
3. [自测手册](../SELF_TEST.md)
4. [学习日志](LEARNING_JOURNAL.md)，只读每周的“问题、原理、数据流、限制”
5. [详细接口文档](API_GUIDE_DETAILED.md)，只读推荐调用流程和 Agent 核心接口
6. [求职材料](JOB_MATERIALS.md)
7. [演示脚本](DEMO_SCRIPT.md)

最短路线仍然必须亲自运行一次项目。只看文档、不操作页面和接口，很难在面试追问中讲清楚。

---

## 10. 最终学习完成标准

满足下面条件，才算真正学会项目：

- [ ] 可以独立启动前端和后端；
- [ ] 可以不看文档完成一次案件分析、追问和报告审批；
- [ ] 可以画出完整 Agent 工作流；
- [ ] 可以从一个接口追踪到服务、数据库和测试；
- [ ] 可以解释 Chat 与 Embedding 的区别；
- [ ] 可以解释离线模式与智能 Agent 模式的区别；
- [ ] 可以解释引用真实性审核；
- [ ] 可以解释 LangGraph interrupt 与恢复；
- [ ] 可以解释报告版本、幂等键和乐观锁；
- [ ] 可以解释法规日期区间和召回前过滤；
- [ ] 可以用 Trace ID 定位节点耗时、模型、Token、费用和降级原因；
- [ ] 可以解释遥测 allowlist 与业务数据的边界；
- [ ] 可以说出当前项目至少 5 个生产化限制；
- [ ] 可以完成 2 分钟项目介绍和 3 分钟项目演示；
- [ ] 可以脱离文档回答主要 Agent、RAG、数据库和工程质量问题。

建议每完成一项就在这里打勾，并把自己答不清的问题记录到学习卡片中。
