# 律镜 Legal Copilot Agent 学习文档与开发日志

## 文档定位

这份文档面向项目作者本人，用于学习项目实现、准备简历和应对技术面试。它和 README 的区别是：README 解决“别人如何启动项目”，本文件解决“我为什么这样设计、代码如何工作、面试时怎么解释”。

文档采用追加式维护。从第三周开始，每完成一组功能就在文件末尾增加新的日期章节，不覆盖之前的学习记录。这样可以保留项目从简单基线演进为完整 Agent 系统的过程，这个演进过程本身也是面试时很有价值的内容。

## 学习方法

建议按以下顺序学习：

1. 先运行项目和接口，不急着阅读全部代码。
2. 从 `app/main.py` 找到一个接口入口。
3. 顺着函数调用查看 service、workflow、model 和 schema。
4. 查看对应测试，理解正常与异常输入的预期行为。
5. 用自己的话复述设计原因，不要只背代码。
6. 修改一个小参数并重新测试，例如 Top-K、检索权重或最大重试次数。
7. 最后阅读面试问答，尝试脱离文档回答。

---

# 2026-07-21：第一周——建立可独立运行的后端与检索基线

## 1. 第一周解决了什么问题

旧项目虽然有多个 Agent，但存在几个不利于求职展示的问题：模块目录包含空格，需要动态导入；法条搜索主要依赖模型记忆；GUI 与核心逻辑耦合；缺少可量化测试；运行需要多个模型服务。

第一周没有直接追求“大模型效果”，而是先建立一个稳定的软件工程底座：

- 项目可以离开旧仓库独立运行；
- 没有 API Key 也可以演示；
- 输入、数据库、检索、API 和测试形成完整闭环；
- 后续加入 Agent 时不会破坏离线基线。

这个顺序很重要。面试官通常更关心系统能否稳定运行、能否测试、失败如何处理，而不是代码里写了几个名为 Agent 的类。

## 2. 第一周项目结构

```text
LegalCopilot-Agent/
├─ app/
│  ├─ main.py                 FastAPI 入口和接口
│  ├─ config.py               环境与路径配置
│  ├─ database.py             SQLAlchemy 引擎和 Session
│  ├─ models.py               数据库表
│  ├─ schemas.py              请求与响应结构
│  └─ services/
│     ├─ document_parser.py   TXT/DOCX/PDF 解析
│     ├─ case_analyzer.py     规则案件分析
│     ├─ embeddings.py        离线哈希向量
│     ├─ retriever.py         第一版向量检索
│     └─ seed.py              样例法规初始化
├─ data/sample_laws.jsonl     项目自己的教学法规
├─ tests/                     自动测试
└─ scripts/run_self_test.py   统一自测入口
```

## 3. 为什么先使用 FastAPI

FastAPI 适合这个项目的原因：

1. Python 生态与 LLM、文档解析、RAG 工具兼容良好。
2. 类型标注和 Pydantic 可以自动进行请求校验。
3. 自动生成 OpenAPI 和 Swagger，方便演示和导入 Apifox。
4. API 层容易与未来 React 前端、任务队列分离。

`app/main.py` 中的 `app = FastAPI(...)` 创建应用。装饰器如 `@app.get`、`@app.post` 将 URL、HTTP 方法和 Python 函数绑定起来。

面试回答要点：FastAPI 不只是“速度快”，更重要的是类型驱动、自动文档和适合异步 I/O。当前工作流仍然同步，第三周才会真正发挥异步接口的价值。

## 4. 为什么使用 Pydantic Schema

`app/schemas.py` 描述了系统允许接收和返回的数据，例如 `CaseFacts`：

```text
case_type            案件类型
parties              当事人
key_facts            关键事实
claims               用户诉求
dispute_focuses      争议焦点
missing_information  缺失信息
questions_for_user   需要确认的问题
```

Schema 的价值：

- API 输出结构稳定，前端不需要猜字段；
- LLM 输出可以经过同一个 Schema 校验；
- 错误数据在进入数据库和业务逻辑前被拦截；
- OpenAPI 可以自动描述字段类型和约束。

一个常见错误是只在提示词中写“请返回 JSON”，然后直接 `json.loads`。JSON 语法正确不代表字段正确，仍需 Pydantic 验证字段、类型、范围和默认值。

## 5. 数据库是如何工作的

`app/database.py` 根据 `DATABASE_URL` 创建 SQLAlchemy Engine。默认地址指向项目内部：

```text
data/legal_copilot.db
```

`SessionLocal` 用于创建数据库会话。FastAPI 的 `get_db()` 使用生成器保证请求结束时关闭 Session。

第一周的主要表：

- `legal_articles`：法规条文和第一版向量；
- `case_runs`：兼容接口产生的案件记录；
- `retrieval_logs`：案件命中了哪些法规以及分数。

选择 SQLite 的原因：

- 求职项目可以直接运行，不要求面试官安装 MySQL；
- 单元测试可以使用内存数据库；
- SQLAlchemy 将数据库实现与业务层隔离；
- 后续仍可迁移 PostgreSQL 或 MySQL。

SQLite 不是最终生产方案。它的并发写能力有限，也没有原生向量索引。当前阶段选择它是为了降低启动成本，而不是认为它适合所有场景。

## 6. 启动时如何自动初始化数据

FastAPI 的 lifespan 会执行以下操作：

1. `Base.metadata.create_all(engine)` 创建不存在的表；
2. `seed_sample_laws(db)` 检查法规表是否为空；
3. 数据为空时读取 `data/sample_laws.jsonl`；
4. 生成本地向量并写入数据库；
5. 第二次启动发现已有数据后跳过导入。

这里体现了幂等性：同一个初始化操作执行多次，最终状态不会重复增长。

面试可能追问：“为什么不用数据库迁移工具？”回答：MVP 使用 `create_all` 降低复杂度；当表结构需要修改或进入团队开发时，应使用 Alembic 保存可追踪的升级和回滚脚本。

## 7. 文档解析流程

入口位于 `app/services/document_parser.py`。

流程：

```text
UploadFile
  ↓ 读取 bytes
根据扩展名分派
  ├─ TXT  → UTF-8 解码
  ├─ DOCX → python-docx 读取段落
  └─ PDF  → pypdf 逐页提取文本
  ↓
统一返回 str
```

为什么不支持旧版 `.doc`：它是二进制格式，跨平台解析经常依赖 Word、LibreOffice 或额外系统程序。MVP 明确拒绝比“偶尔成功、偶尔失败”更可靠。

为什么扫描 PDF 无法读取：`pypdf` 读取的是 PDF 中已有的文本层。如果 PDF 每页只是图片，需要 OCR，这是后续扩展点。

安全注意：扩展名检查只是第一层。第三周还应加入 MIME、文件头、文件大小、页数、解析时间和保存路径校验。

## 8. 规则案件分析基线

`app/services/case_analyzer.py` 不调用模型，而是通过关键词和正则表达式完成基础抽取。

例如：

- 出现“劳动、工资、加班”倾向劳动争议；
- 出现“合同、违约、货款”倾向合同纠纷；
- 使用“原告、被告、甲方、乙方”等标签提取当事人；
- 使用“请求、赔偿、支付、返还、解除”筛选诉求；
- 使用“争议、是否、违约、责任”筛选争议焦点。

规则方案明显不够智能，为什么还要保留：

1. 没有密钥时项目仍可运行；
2. 模型故障时可以降级；
3. 为评测提供基线；
4. 规则输出可重复，方便定位系统其他部分的问题。

这是工程中的 baseline 思维：先建立一个简单、可复现的最低效果，再证明复杂方案确实带来了提升。

## 9. 第一版离线向量

`app/services/embeddings.py` 实现中文二元字符哈希向量：

1. 删除空格并转为小写；
2. 将“合同违约赔偿”切成“合同、同违、违约、约赔、赔偿”；
3. 对每个片段计算 SHA-256；
4. 将结果映射到固定的 384 个维度；
5. 累加并进行 L2 归一化；
6. 使用余弦相似度计算接近程度。

余弦相似度的直观含义：比较两个向量方向是否接近。公式是：

```text
cos(A, B) = (A · B) / (||A|| × ||B||)
```

由于向量已经归一化，代码中可以直接计算点积。

这不是真正语义模型。它主要识别字符片段重合，无法很好理解同义词。但它无需网络、结果确定、速度快，适合作为第一版可运行基线。

## 10. 第一周 API 流程

以 `POST /api/v1/cases` 为例：

```text
接收 question 和 file
  ↓
解析文件文本
  ↓
规则提取 CaseFacts
  ↓
组合问题和争议焦点
  ↓
检索 Top-K 法规
  ↓
保存 CaseRun 和 RetrievalLog
  ↓
返回 run_id、facts、citations、notice
```

这条接口是同步接口，适合第一周快速验证。第三周会将长工作流改成“创建任务后立即返回 run_id，再轮询状态”。

## 11. 第一周如何测试

统一执行：

```powershell
python scripts\run_self_test.py
```

第一周测试覆盖：案件分类、TXT 解析、非法格式、向量相关性、健康检查、法规搜索和案件分析接口。

为什么脚本使用标准库 unittest：降低新环境测试门槛，不需要额外安装 pytest。项目后续仍可迁移 pytest，以使用 fixture、参数化和插件生态。

## 12. 第一周面试表达

可以这样介绍：

> 我先将原来的多模型 GUI 原型拆成独立 FastAPI 服务，以 SQLite 和离线检索建立可复现基线。系统支持案件文件解析、结构化要素提取、法规检索和引用返回，并通过自动测试保证无模型密钥时仍可运行。这为后续 Agent 编排和效果评测提供了稳定底座。

---

# 2026-07-21：第二周——从检索基线升级为可控 Agent 工作流

## 1. 第二周解决了什么问题

第一周只能返回案件要素和候选法条，缺少以下能力：

- 无法调用真实 LLM 进行更好的事实理解；
- 检索只有单一分数；
- 没有验证模型或检索结果中的法条是否真实；
- 没有清晰的多步骤状态和重试分支；
- 没有生成最终报告；
- 模型超时或返回错误 JSON 时没有统一回退机制。

第二周围绕“可控”展开。这里的 Agent 不是让模型自由决定一切，而是将模型放入受约束的工作流节点中。

## 2. 第二周新增结构

```text
app/
├─ llm/
│  └─ client.py                  OpenAI 兼容结构化 LLM 客户端
├─ services/
│  ├─ embedding_provider.py      Embedding 抽象与实现
│  ├─ embedding_index.py         多模型向量索引
│  ├─ legal_chunker.py           长法条切片
│  ├─ mixed_retriever.py         关键词 + 语义混合检索
│  ├─ case_agent.py              LLM 案件分析及规则回退
│  ├─ citation_reviewer.py       引用真实性和语义审核
│  └─ report_writer.py           报告草稿与 Markdown 渲染
├─ workflows/
│  └─ legal_report_graph.py      LangGraph 状态图
└─ models.py                     AgentRun 等新增表
```

## 3. 配置层与 Adapter 模式

真实项目不应让业务代码直接依赖某一家模型 SDK。当前项目定义了适配层：

- LLM 对外提供 `invoke_structured`；
- Embedding 对外提供 `embed_documents` 和 `embed_query`；
- 业务服务只依赖这些稳定方法。

好处：

1. 更换 DeepSeek、OpenAI 或其他兼容服务时不改业务节点；
2. 测试可以替换为 Fake 或 Mock；
3. 离线实现和真实实现可以共用一套调用方式；
4. 错误可以统一转换为项目自己的异常类型。

当前配置兼容两组变量：

```text
LLM_API_KEY      或 OPENAI_API_KEY
LLM_BASE_URL     或 OPENAI_BASE_URL
LLM_MODEL        或 MODEL_NAME
```

项目不会把真实密钥写进代码。`.env.example` 只包含占位符，真实值放在被 Git 忽略的 `.env`。

## 4. LLM 结构化输出与有限重试

`app/llm/client.py` 使用 OpenAI 兼容的 `/chat/completions` 接口。

一次调用包括：

1. system prompt 明确节点职责和 JSON 字段；
2. `response_format=json_object` 请求 JSON；
3. 提取代码块或正文中的 JSON 对象；
4. 使用 Pydantic Schema 校验；
5. 首次格式错误时请求模型修复一次；
6. 第二次仍失败则抛出 `LLM_INVALID_OUTPUT`；
7. 上层 Agent 捕获错误并回退规则方案。

为什么只能修复一次：无限重试会带来不可控的延迟、费用和死循环。明确的重试上限比“直到成功”为止更适合生产系统。

错误被分为：认证失败、限流、服务端错误、网络/超时、HTTP 错误和结构化输出错误。可重试错误只做有限重试，认证错误不重试。

## 5. 多 Embedding 索引设计

第一周把向量直接放在法规表中。第二周增加 `article_embeddings`：

```text
article_id
provider
model
dimensions
content_hash
vector
```

这允许同一条法规同时保存哈希向量和真实模型向量。

`content_hash` 用于判断正文是否变化：

- 正文和 provider/model 都不变：跳过计算；
- 正文变化：重新生成；
- 切换模型：生成一套新的索引；
- 重复执行脚本：不会重复写入。

这种能力叫幂等索引或增量索引。真实知识库可能有大量文档，不能每次启动都重新付费计算全部 Embedding。

索引命令：

```powershell
python scripts\reindex_embeddings.py
```

## 6. 为什么 Chat 模型与 Embedding 要分开配置

Chat 模型处理自然语言理解和生成；Embedding 模型把文本转换为向量。两者经常由不同服务提供。

不能因为某服务兼容 `/chat/completions`，就假设它一定支持 `/embeddings`。项目因此使用独立配置：

```text
LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
```

默认 `EMBEDDING_PROVIDER=hash`，即使启用 DeepSeek Chat，也不会错误地向 DeepSeek 地址发送 Embedding 请求。

## 7. 长法条切片

`app/services/legal_chunker.py` 对超长法条执行：

1. 清理空行；
2. 长度不超过阈值时保持整条；
3. 优先在换行、句号或分号边界切分；
4. 相邻切片保留少量重叠；
5. 每个切片保留原始条号和稳定 `chunk_index`。

重叠的意义：如果重要语义刚好位于切分边界，两边都保留一部分上下文，可以减少检索遗漏。

法律文本切片不能随意把不同条号混在一起，因为最终引用必须能准确回到具体法条。

## 8. 混合检索原理

`app/services/mixed_retriever.py` 同时计算：

- `keyword_score`：查询与法条二元片段的覆盖程度，并对法律名称、条号精确命中加分；
- `semantic_score`：查询向量与法规向量的余弦相似度；
- `score`：两种分数按权重融合。

公式：

```text
combined_score = keyword_weight × keyword_score
               + semantic_weight × semantic_score
```

默认权重：关键词 0.35，语义 0.65。配置层会自动归一化权重，避免用户填写的权重和不等于 1。

为什么不只用向量：法条号、法律名称和固定术语非常适合精确匹配。为什么不只用关键词：用户可能使用不同表述，真实 Embedding 更擅长理解语义接近。混合检索结合两者优势。

## 9. 案件分析 Agent

`app/services/case_agent.py` 的策略：

```text
有可用 LLM
  ↓
调用结构化案件抽取
  ├─ 成功 → source=llm
  └─ 失败 → 规则抽取，source=rules_fallback，并记录原因

无 LLM 或 offline
  ↓
规则抽取，source=rules
```

提示词明确要求“只能依据材料，不得补充事实”。Schema 增加置信度、缺失信息和待确认问题，以便模型承认材料不足，而不是强行生成完整故事。

## 10. LangGraph 状态设计

`WorkflowState` 是节点共享的数据结构，主要字段：

```text
run_id                 任务 ID
document_text           文件文本
question                用户问题
mode                    offline/agent
facts                   结构化案件事实
retrieval_query         实际检索查询
citations               候选引用
reviewed_citations      审核引用
retry_count             补充检索次数
traces                  节点轨迹
report_title            报告标题
report_markdown         Markdown 报告
evidence_gaps           证据缺口
model_name              实际模型
```

节点函数遵循 `State → Partial State`：读取当前状态，只返回需要更新的字段。这样每个节点职责清晰，方便单独测试和增加条件分支。

## 11. 工作流节点与条件边

当前状态图：

```text
START
  ↓
analyze_case
  ↓
retrieve_laws
  ↓
review_citations
  ├─ 有 verified 引用 ─────────→ write_report → END
  ├─ 无引用且 retry < 2 → retry_retrieval ─┐
  │                                         └→ retrieve_laws
  └─ 无引用且 retry = 2 ──────→ write_report → END
```

这段图体现了 Agent 工作流的核心：节点不仅顺序执行，还根据当前状态决定下一步，并能使用工具和重试。但决策范围是工程师明确设计的，不是任由模型调用任意工具。

## 12. Agent 与普通流水线的区别

普通流水线通常固定执行 A → B → C。当前工作流有状态、条件边、工具调用、失败回退和有限循环，因此具备 Agent 工作流特征。

但不要夸大：当前并不是完全自治 Agent。它更准确地说是“受控的 Agentic Workflow”。面试中这样描述会比“多个智能体自动辩论”更可信。

## 13. 两层引用审核

引用审核位于 `app/services/citation_reviewer.py`。

第一层是确定性校验：

1. `article_id` 在数据库中存在；
2. 法律名称一致；
3. 条号一致；
4. 引用正文与数据库原文完全一致；
5. 查询与条文具有最低检索关联。

任意关键字段不一致，引用标记为 `rejected`。这可以拦截模型虚构或篡改法条。

第二层是可选 LLM 语义审核：判断真实条文是否能支撑当前问题。LLM 只能审核给定 ID，不能新增法条。模型可以将引用降级为低置信度，但不能绕过第一层真实性校验。

关键设计原则：确定性规则管理“它是不是真实条文”，模型辅助判断“它是否支持当前论点”。

## 14. 报告生成为何分为 Draft 和 Render

`app/services/report_writer.py` 分两步：

1. `create_report_draft` 生成标题、分析、建议和证据缺口；
2. `render_markdown` 由服务器拼装固定章节、免责声明和数据库引用原文。

不让模型直接生成完整最终 Markdown 的原因：

- 模型可能修改法条原文；
- 模型可能漏掉免责声明；
- 输出章节和引用格式不稳定；
- 服务端渲染更容易测试。

模型失败时使用离线模板生成报告。没有通过审核的引用时，报告明确写“低置信度”，而不是隐藏事实。

## 15. 第二周新增数据库表

### `agent_runs`

保存任务问题、文件文本、模式、状态、进度、当前节点、重试次数、事实、报告、节点轨迹、错误、模型名称和时间。

### `agent_run_citations`

保存任务与法规的关系，以及综合分数、关键词分数、语义分数、审核状态、审核理由和最终是否通过。

### `article_embeddings`

保存每个 provider/model 对应的法规向量和内容哈希。

这些表让一次 Agent 运行变得可追踪：不仅知道最终报告是什么，也知道它检索了什么、为什么通过、是否回退、每个节点花了多久。

## 16. 第二周 API 调用流程

创建任务：

```text
POST /api/v1/runs
question=供应商收款后没有交货，能否解除合同并要求赔偿？
mode=offline
```

返回：

```json
{
  "run_id": 1,
  "status": "completed",
  "status_url": "/api/v1/runs/1",
  "report_url": "/api/v1/runs/1/report"
}
```

然后调用：

```text
GET /api/v1/runs/1             查看状态、事实和节点轨迹
GET /api/v1/runs/1/citations   查看引用与审核结果
GET /api/v1/runs/1/report      查看最终报告
GET /api/v1/articles/{id}      回查引用原文
```

当前 `POST /runs` 虽然返回 202，但第二周仍在请求内同步执行。第三周会改为真正后台任务，接口路径保持不变。

## 17. 节点轨迹是什么

每个节点记录：

- 节点名称；
- 完成或失败状态；
- 执行耗时；
- 可以公开的动作摘要；
- 错误码。

项目不会保存或展示模型隐藏思维链。可观测性应该记录输入输出摘要、工具动作、耗时和错误，而不是要求模型暴露完整内部推理。

## 18. 第二周故障处理

### 没有 API Key

Agent 模式会发现 LLM 不可用，使用规则和模板继续完成。

### 模型超时

客户端有限重试，仍失败则上层回退。

### 模型返回非法 JSON

请求修复一次；仍失败则抛出结构化错误并回退。

### Embedding 服务未配置

默认使用 hash provider。真实 Embedding 必须单独配置，不能默认复用 Chat 地址。

### 没有检索结果

工作流最多补充检索两次，然后生成低置信度报告并结束。

### 引用被篡改

数据库一致性校验失败，标记 `rejected`，不会进入报告的可信引用部分。

## 19. 第二周测试覆盖

当前共有 19 项自动测试，重点包括：

- 合同和劳动案件分类；
- 文档解析与非法格式；
- 哈希向量与混合检索；
- 向量索引幂等；
- 长法条切片；
- 篡改引用拦截；
- 无知识库时有限重试；
- LLM 超时回退；
- 非法 JSON 只修复一次；
- OpenAI 兼容环境变量映射；
- LangGraph 节点顺序；
- 状态、引用、报告和法条详情接口；
- 无密钥 Agent 模式回退。

执行：

```powershell
python scripts\run_self_test.py
```

预期：

```text
Ran 19 tests
OK
```

## 20. 第二周面试表达

可以这样介绍：

> 第二阶段我用 LangGraph 将案件分析、混合检索、引用审核和报告生成建模为显式状态图。系统同时支持离线和真实模型模式，通过 Adapter 隔离服务商，通过 Pydantic 校验结构化输出。所有法条引用先用数据库 ID 和原文做确定性校验，再进行可选语义审核；模型或检索失败时采用有限重试和规则回退，避免无限循环和单点故障。

---

# 求职面试复习区

## 1. 为什么这个项目需要 RAG

LLM 参数中的知识无法保证准确、最新和可追溯。RAG 先从项目知识库检索候选依据，再让模型基于依据分析，可以降低凭空生成法条的概率，并提供可回查引用。

注意：RAG 不能自动消除幻觉。检索可能返回错误内容，模型也可能错误理解，因此项目增加引用审核和评测。

## 2. 为什么需要 LangGraph

工作流包含状态共享、条件分支、工具调用、失败回退和有限循环。手写大量 if/else 也能实现，但随着节点增加会难以维护。LangGraph 将节点、边和状态显式化，便于解释、测试和未来加入持久化或人工审核。

## 3. 如何防止法条幻觉

回答顺序：

1. 法条来自数据库检索，不接受模型自由生成的法条作为事实。
2. 报告引用必须包含 `article_id`。
3. 服务端回查法律名称、条号和正文。
4. 不一致的引用直接拒绝。
5. 模型只能判断支撑关系，不能修改原文。
6. 最终报告附来源和免责声明。
7. 使用人工标注评测集计算引用正确率。

## 4. 为什么保留 Offline 模式

- 提高可运行性；
- 降低演示成本；
- 支持 CI；
- 建立效果基线；
- 外部模型故障时提供降级能力。

## 5. 为什么当前不用 MySQL

SQLite 能让项目独立运行，适合单机 MVP 和测试。进入多用户并发、后台任务和生产部署后，可以迁移 PostgreSQL/MySQL。数据库选择应由阶段和负载决定，不是越复杂越专业。

## 6. 为什么当前不用 Redis 和 RocketMQ

第二周任务同步执行，不需要消息代理。第三周做后台任务时 Redis 可用于队列、状态和限流。RocketMQ 更适合与已有 Java 微服务事件体系集成，当前引入会增加运维复杂度而没有直接收益。

## 7. 当前检索有什么不足

- 内置法规只有少量教学样例；
- 哈希向量主要依赖字符重合；
- 没有 BM25、向量数据库和 reranker；
- 没有法规时效性和版本过滤；
- 尚未通过完整标注集评测。

面试时不要回避限制。说明下一步如何验证和改进，比声称“检索很准确”更专业。

## 8. Agent 和普通 LLM 调用有什么区别

普通调用是输入 Prompt 后得到一次输出。本项目将模型放在有状态工作流中，能够调用检索和审核工具，根据结果选择重试或继续，并持久化执行轨迹。它仍然是受控工作流，不是无限自治。

## 9. 为什么不保存思维链

工程可观测性需要的是可验证的动作摘要、工具输入输出、耗时、错误和决策结果。隐藏思维链不稳定、不可作为可靠审计依据，也可能包含敏感信息。项目只记录公开节点轨迹。

## 10. 当前最大的技术债是什么

可以回答：

1. 后台任务仍然同步；
2. 数据库没有 Alembic 迁移；
3. 法规数据量和权威性不足；
4. 真实 Embedding 尚未形成固定评测结果；
5. 没有前端和 Docker；
6. 错误响应格式还未完全统一。

这些正是第三、第四周要解决的问题。

## 11. 简历描述草稿

在完成第四周评测前，不填写虚构指标。当前可以使用：

> 独立设计并实现可追溯法律分析 Agent，使用 FastAPI、SQLAlchemy 与 LangGraph 构建案件分析、混合检索、引用审核和报告生成工作流；通过 Adapter 支持离线与 OpenAI 兼容模型切换，并以 Pydantic 校验、有限重试和规则回退处理模型异常。所有法规引用均通过数据库 ID 与原文一致性审核，项目提供 OpenAPI/Apifox 文档及 19 项自动测试。

第四周获得真实评测结果后，再加入 Recall@5、引用正确率、工作流成功率和 P95 延迟。

---

# 后续追加格式

以后每次完成一组功能，在文件末尾复制以下模板并填写，不修改上面的历史章节。

```markdown
# YYYY-MM-DD：第 N 周——功能名称

## 1. 本次解决的问题

## 2. 用户可以看到的变化

## 3. 新增或修改的文件

## 4. 核心实现原理

## 5. 一次请求或数据的完整流转

## 6. 异常与安全处理

## 7. 自动测试和实际结果

## 8. 已知限制和下一步

## 9. 面试可能追问

## 10. 本次简历描述是否需要更新
```

---

# 2026-07-22：配置兼容与学习文档制度

## 1. 本次解决的问题

用户已有一套 OpenAI 兼容、MySQL、Redis、Spring Boot 和 RocketMQ 配置，需要判断哪些可以用于当前 Python Agent 项目。同时需要建立一份以求职学习为目标、以后持续追加的项目文档。

## 2. 用户可以看到的变化

- 项目支持直接读取 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MODEL_NAME`；
- 原来的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 仍然支持；
- Chat 和 Embedding 配置彻底分离；
- 新增 `docs/CONFIGURATION.md`；
- 新增本学习日志；
- 新增 `AGENTS.md`，要求以后完成功能后追加学习记录。

## 3. 新增或修改的文件

- `app/config.py`：增加兼容变量读取和优先级；
- `.env.example`：更新 DeepSeek 示例并增加安全提醒；
- `docs/CONFIGURATION.md`：解释各类旧配置是否适用；
- `tests/test_second_week.py`：验证环境变量别名；
- `docs/LEARNING_JOURNAL.md`：项目学习与面试准备主文档；
- `AGENTS.md`：追加式维护规则。

## 4. 核心实现原理

配置读取使用“新项目变量优先，兼容变量兜底”的方式：

```text
LLM_API_KEY  > OPENAI_API_KEY
LLM_BASE_URL > OPENAI_BASE_URL
LLM_MODEL    > MODEL_NAME
```

这样不会强迫已有环境立刻改名，同时避免业务代码到处判断不同变量。

Embedding 不复用 LLM Key 和地址。只有用户显式配置 `EMBEDDING_PROVIDER=openai-compatible` 以及独立 Embedding 参数时，系统才请求 `/embeddings`。

## 5. 一次配置读取的流转

```text
Python 导入 app.config
  ↓
读取项目根目录 .env
  ↓
读取系统环境变量
  ↓
按优先级选择 LLM 配置
  ↓
校验检索权重并归一化
  ↓
缓存 Settings
  ↓
LLM/Embedding Adapter 使用 Settings
```

由于 `get_settings()` 使用缓存，修改 `.env` 后必须重新启动服务。

## 6. 异常与安全处理

- 真实密钥和密码不写入仓库；
- `.env` 被 `.gitignore` 排除；
- 已公开的密钥应在服务提供方撤销并轮换；
- MySQL、Redis、RocketMQ 配置未直接搬入项目；
- 不把 Spring JDBC URL 当作 SQLAlchemy URL；
- 不把 Chat 模型地址自动当作 Embedding 地址。

## 7. 自动测试和实际结果

新增 `test_openai_compatible_environment_aliases`，在隔离的环境变量中验证兼容名称、优先级、模型名、离线模式和 Embedding 密钥隔离。

完整测试结果：

```text
Ran 19 tests
OK
```

## 8. 已知限制和下一步

当前没有迁移 MySQL，也没有接入 Redis/RocketMQ。第三周实现后台任务时再评估 Redis；只有需要对接已有 Java 事件系统时才考虑 RocketMQ。

## 9. 面试可能追问

问题：“为什么不直接兼容所有旧配置？”

回答要点：配置兼容不是越多越好。只兼容语义相同的 OpenAI Chat 参数；数据库、中间件和 Java 框架配置涉及不同运行模型，必须经过架构设计和迁移验证，不能简单改名后使用。

问题：“为什么修改 `.env` 后需要重启？”

回答要点：配置对象通过 `lru_cache` 缓存，减少重复读取和解析；重启进程会清空缓存并加载新配置。测试中通过 `cache_clear()` 隔离不同环境。

## 10. 本次简历描述是否需要更新

不需要单独增加简历条目。它属于“支持 OpenAI 兼容模型切换和安全配置管理”的实现细节，可以在面试展开说明。

---

# 2026-07-22：逐接口使用手册

## 1. 本次解决的问题

原有 `API_REFERENCE.md` 和 `openapi.json` 适合快速查阅和导入工具，但学习者仍需要理解每个接口为什么存在、参数如何填写、返回字段如何解释、出错后如何排查，以及多个接口之间怎样组成完整 Agent 调用链。

## 2. 用户可以看到的变化

- 新增 `docs/API_GUIDE_DETAILED.md`，覆盖全部 15 个接口定义；
- 9 个已实现接口包含真实调用方式、详细字段说明、成功和错误返回示例；
- 6 个规划接口包含预期契约，并明确提示当前调用会返回 404；
- 增加 Apifox 环境配置、完整自测顺序、统一错误理解和面试回答；
- README 与快速接口文档增加详细手册入口。

## 3. 新增或修改的文件

- `docs/API_GUIDE_DETAILED.md`：逐接口学习与调试主文档；
- `README.md`：增加详细接口手册链接；
- `docs/API_REFERENCE.md`：增加从快速参考到详细手册的跳转；
- `docs/LEARNING_JOURNAL.md`：追加本次学习记录。

## 4. 核心文档设计原则

接口文档不能只写 URL。一个可用于开发协作和求职学习的接口说明至少需要回答六个问题：它解决什么业务问题、怎样发请求、字段有什么约束、成功后返回什么、失败后怎样处理、下一步调用哪个接口。

文档严格区分 `implemented` 和 `planned`。规划接口的示例是契约设计，不是伪装成已经完成的运行结果，这能避免调试时把正常的 404 误判为环境故障。

## 5. 一次 Agent 请求的完整流转

```text
POST /api/v1/runs
  → 返回并保存 run_id
GET /api/v1/runs/{run_id}
  → 查看状态、进度和节点轨迹
GET /api/v1/runs/{run_id}/citations
  → 审核法规来源和分数
GET /api/v1/runs/{run_id}/report
  → 获取 Markdown 与结构化报告
```

`run_id` 把一次创建请求与后续状态、引用、报告资源关联起来。重试失败任务会产生新的 `run_id`，不会覆盖原失败记录。

## 6. 异常与安全处理

- 明确解释 404、409、415、422 等状态码和排查动作；
- 指出 FastAPI 当前默认错误格式与规划统一错误格式的差异；
- 规划接口当前返回 404 属于预期行为；
- 示例只使用假数据，不包含真实密钥、数据库密码或案件材料；
- 法规引用的相关度分数不能解释为结论正确率或胜诉率。

## 7. 验证结果

本次只新增和更新 Markdown 文档，没有修改运行代码或 OpenAPI 契约。接口数量已与 `docs/openapi.json` 对照：共 15 个，其中 9 个 `implemented`、6 个 `planned`。

## 8. 已知限制和下一步

规划接口需要在后续周次实现后，把文档里的“计划返回”替换为自动测试验证过的真实结果。第三周异步化后，还需要补充轮询间隔、任务超时和幂等性说明。

## 9. 面试可能追问

问题：“为什么创建任务、查询状态、查询引用和获取报告要拆成多个接口？”

回答要点：Agent 任务可能耗时且失败，拆分资源后可以支持进度轮询、失败重试、引用审计、报告权限与独立导出，也为同步实现迁移到后台任务保留稳定契约。

问题：“为什么要把规划接口也写进 OpenAPI？”

回答要点：先设计契约可以让前后端并行和提前 Mock，但必须通过扩展字段清楚标记实现状态，避免把设计稿误认为生产能力。

## 10. 本次简历描述是否需要更新

不需要新增独立简历条目。接口契约设计、错误处理、可观测任务资源和 Apifox/OpenAPI 协作方式可以作为现有 Agent 项目的面试展开内容。

---

# 2026-07-22：本地运行环境文件

## 1. 本次解决的问题

为项目创建实际使用的 `.env`，让 PyCharm 启动时能够从项目根目录读取一套明确、安全且可以直接运行的配置。

## 2. 用户可以看到的变化

- 默认 `OFFLINE_MODE=true`，没有模型密钥也能完成 Agent 工作流；
- 默认使用项目自己的 SQLite，不依赖 MySQL；
- 默认使用本地哈希 Embedding，不调用外部向量接口；
- 预填 DeepSeek 兼容地址和模型名，但密钥保持为空；
- 保留混合检索权重、超时和工作流重试次数。

## 3. 新增或修改的文件

- `.env`：本机运行配置，被 `.gitignore` 排除；
- `docs/LEARNING_JOURNAL.md`：追加本次配置学习记录。

## 4. 核心实现原理

`app/config.py` 在导入时读取项目根目录的 `.env`，再构造并缓存 `Settings`。`DATABASE_URL` 留空时自动使用 `data/legal_copilot.db`；`EMBEDDING_PROVIDER=hash` 时使用本地哈希向量；`OFFLINE_MODE=true` 时不调用外部 LLM。

## 5. 配置读取流转

```text
启动 app.main
  → app.config 加载项目根目录 .env
  → get_settings() 校验和归一化配置
  → 数据库选择 SQLite
  → Embedding 选择 hash
  → Agent 选择 offline
  → 服务无需外部中间件即可启动
```

## 6. 异常与安全处理

- `.env` 已由 `.gitignore` 排除，不应提交到 Git；
- 公开粘贴过的 API Key 不再写入文件，应先撤销并轮换；
- MySQL、Redis、RocketMQ 当前未接入，不保存相关密码；
- 切换真实模型时只填写轮换后的 `LLM_API_KEY`，并把 `OFFLINE_MODE` 改为 `false`；
- 修改 `.env` 后需要重启 PyCharm 中的服务，因为 Settings 有进程内缓存。

## 7. 验证结果

配置项与 `app/config.py` 当前读取字段逐项核对。离线组合不要求网络、API Key、MySQL、Redis 或 RocketMQ。

## 8. 已知限制和下一步

当前 DeepSeek 模型配置只用于 OpenAI 兼容 Chat。Embedding 继续使用本地 hash；如果以后切换真实 Embedding，需要单独确认服务是否提供 Embedding 模型，并填写独立的 Key、Base URL 和模型名。

## 9. 面试可能追问

问题：“为什么 Chat 模型和 Embedding 不共用一套配置？”

回答要点：二者可能来自不同供应商、使用不同模型和鉴权策略。拆分配置可以避免把只支持 Chat 的地址错误用于 Embedding，也方便独立降级和成本控制。

## 10. 本次简历描述是否需要更新

不需要。环境分层、安全密钥管理和离线降级属于项目工程化设计，可在面试中结合整体架构说明。

---

# 2026-07-22：第三周——可交互产品、后台任务与报告导出

## 1. 本次解决的问题

第二周已经具备完整 Agent 工作流，但用户只能通过 Swagger 或 Apifox 操作，而且创建任务会在一个请求内等待工作流完成。第三周把技术能力包装为可演示的浏览器产品，并补齐长任务进度、文件安全、报告下载、请求日志和容器化配置。

第三周的核心目标不是简单“增加一个页面”，而是建立以下完整闭环：

```text
浏览器输入问题/上传文件
  → 后端校验文件并创建 queued 任务
  → HTTP 202 立即返回 run_id
  → FastAPI 后台任务执行 LangGraph
  → 每个节点把状态和进度写入 SQLite
  → React 每 1.5 秒轮询状态
  → completed 后并行读取报告和引用
  → 用户查看引用详情并下载 Markdown/PDF
```

## 2. 用户可以看到的变化

- 新增完整 React + TypeScript 页面，不再依赖 Swagger 完成演示；
- 支持拖拽或点击上传 TXT、DOCX、PDF，并显示名称、类型和大小；
- 支持示例问题、5000 字限制、离线/Agent 模式切换；
- 创建任务立即返回 `queued`，页面持续显示节点与进度；
- 展示案件类型、置信度、四个节点的动作摘要和耗时；
- 报告使用安全 Markdown 组件渲染，不执行用户 HTML；
- 点击引用可查看数据库原文、来源、各检索分数和审核理由；
- 支持下载 `.md` 和带中文字体的 `.pdf` 报告；
- 后端离线时页面会明确提示，提交按钮不会继续发送无效请求；
- 提供 Docker Compose 配置，可在安装 Docker 后启动前后端。

## 3. 新增或修改的关键文件

### 后端

- `app/main.py`：后台任务、CORS、请求日志、安全上传和报告导出路由；
- `app/tasks.py`：使用独立数据库 Session 执行后台 Agent 任务；
- `app/workflows/legal_report_graph.py`：逐节点持久化状态、进度和轨迹；
- `app/services/upload_security.py`：文件大小、扩展名、MIME、文件名和解析超时校验；
- `app/services/report_export.py`：把 Markdown 转换为中文 PDF；
- `app/migrations.py`：为已有 SQLite 数据库补充 `started_at` 字段；
- `app/models.py`、`app/schemas.py`：增加任务时间信息；
- `tests/test_third_week.py`：第三周接口、安全和导出测试。

### 前端

- `frontend/src/App.tsx`：输入、上传、轮询、轨迹、报告和引用交互；
- `frontend/src/api.ts`：统一 API 调用和错误转换；
- `frontend/src/types.ts`：与后端响应对应的 TypeScript 类型；
- `frontend/src/styles.css`：响应式产品视觉与可访问性样式；
- `frontend/vite.config.ts`：本地开发代理；
- `frontend/package.json`、`pnpm-lock.yaml`：可复现依赖与构建命令。

### 部署与文档

- `Dockerfile`：后端生产镜像；
- `frontend/Dockerfile`、`frontend/nginx.conf`：前端构建和反向代理；
- `docker-compose.yml`：前后端、健康检查和 SQLite volume；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：同步第三周状态与操作；
- `docs/openapi.json`、`docs/API_REFERENCE.md`、`docs/API_GUIDE_DETAILED.md`：导出接口改为已实现，更新异步语义。

## 4. 核心实现原理

### 4.1 为什么创建接口只返回 queued

`POST /api/v1/runs` 的职责变成“创建任务资源”，而不是“等待所有分析完成”。路由先把问题、文件文本和模式写入 `agent_runs`，提交事务取得 `run_id`，再把 `execute_agent_run_by_id` 注册为 FastAPI BackgroundTask。

响应使用 HTTP 202：

```json
{
  "run_id": 42,
  "status": "queued",
  "status_url": "/api/v1/runs/42",
  "report_url": "/api/v1/runs/42/report"
}
```

后台函数不能复用请求中的 SQLAlchemy Session，因为请求结束后该 Session 会关闭。因此 `app/tasks.py` 根据 `run_id` 创建独立 Session，再读取任务并执行工作流。

### 4.2 节点进度如何保存

LangGraph 每个节点开始和结束时更新 `AgentRun`：

| 状态 | 典型进度 | 节点 |
|---|---:|---|
| `queued` | 0 | 等待后台执行 |
| `analyzing` | 15–30 | `analyze_case` |
| `retrieving` | 40–55 | `retrieve_laws` |
| `reviewing` | 65–75 | `review_citations` |
| `writing` | 85–95 | `write_report` |
| `completed` | 100 | 工作流结束 |

每个节点把公开动作摘要和耗时写入 `node_traces`。这里只展示“做了什么”和“花了多久”，不展示模型隐藏思维链。

### 4.3 前端为什么轮询而不是 WebSocket

当前任务量小、状态更新频率低，1.5 秒 HTTP 轮询更容易实现、测试和部署。组件在任务完成、失败或卸载时清理 `setInterval`，避免内存泄漏和无效请求。

WebSocket 或 SSE 更适合高频实时事件，但会增加连接管理、断线恢复和代理配置。当前阶段轮询的复杂度与收益更合理。

### 4.4 Markdown 为什么使用 ReactMarkdown

报告内容来自模型或模板，必须按不可信输入处理。`react-markdown` 默认不会直接执行原始 HTML，比把字符串交给 `dangerouslySetInnerHTML` 更安全。正式产品仍应增加内容安全策略和链接协议白名单。

### 4.5 PDF 如何支持中文

后端使用 ReportLab 的 `STSong-Light` CID 字体构建 PDF。它避免依赖开发机的 Windows 字体路径，使 Linux 容器也能生成中文。转换器识别 Markdown 标题、引用和列表，其他文本按段落写入。

## 5. 一次请求和数据的完整流转

```text
用户拖入 case.pdf
  → 前端检查扩展名、大小和空文件
  → FormData 提交 question/mode/file
  → 后端最多读取 MAX_UPLOAD_BYTES + 1
  → 校验扩展名与 MIME 对应关系
  → 在线程中解析文档，并设置超时
  → 保存 AgentRun(status=queued)
  → 响应 202 + run_id
  → 后台线程使用新 Session 执行 LangGraph
  → 状态接口读取 SQLite 中的实时状态
  → 前端轮询到 completed
  → 并行读取 report 与 citations
  → ReactMarkdown 渲染正文
  → 用户点击 citation 查看可追溯原文
```

导出请求不会重新运行模型，而是读取数据库中已经保存的 `report_markdown`。这样能保证页面展示和下载文件使用同一份结果，也避免重复费用。

## 6. 异常与安全处理

### 上传安全

- 前后端都限制最大 10 MB，前端校验只改善体验，后端校验才是安全边界；
- 允许 `.txt`、`.docx`、`.pdf`，同时检查浏览器上报的 MIME；
- 只读取 `MAX_UPLOAD_BYTES + 1`，不会先把任意大文件完整放进内存；
- 使用安全展示文件名，去除目录和特殊字符；
- 当前不把上传文件保存到服务器，降低路径穿越和残留风险；
- 空文件、损坏文件和解析超时分别返回可理解错误。

### 日志安全

每次 HTTP 请求获得或复用 `X-Request-ID`，日志记录 method、path、status code 和 duration。日志不记录 Authorization、API Key、文件全文或问题全文。

### 后台任务限制

FastAPI BackgroundTasks 是进程内方案。它解决 HTTP 长时间阻塞，但不能保证服务崩溃后的任务恢复，也不能跨多个实例统一调度。生产环境应迁移到 Celery/RQ + Redis 等持久队列，并增加幂等键和任务租约。

## 7. 自动测试和实际结果

后端执行：

```powershell
python scripts\run_self_test.py
```

实际结果：

```text
Ran 26 tests
OK
```

第三周新增测试覆盖：

- 创建响应为 `queued`，后台完成后状态为 `completed`；
- 开始和完成时间写入；
- Markdown 导出文件名、Content-Type 和正文；
- PDF 以 `%PDF` 文件头返回且包含有效内容；
- 非法导出格式返回 422；
- 扩展名/MIME 伪装返回 415；
- 文件名目录部分与危险字符被清理；
- `X-Request-ID` 在响应中返回。

前端执行 TypeScript 检查和 Vite 生产构建，实际结果为 188 个模块转换成功，生成 HTML、CSS 和 JavaScript 生产文件。

OpenAPI JSON 解析通过：版本 `0.3.0`，15 个契约中 10 个 implemented、5 个 planned。Docker Compose YAML 结构解析通过，包含 backend、frontend 和 legal-data volume。

## 8. 已知限制和下一步

- 当前电脑没有安装 Docker，所以 Dockerfile/Compose 尚未执行真实镜像构建；
- BackgroundTasks 不持久，第四周或生产化时可迁移任务队列；
- 前端没有用户账号，任何能访问服务的人都能通过 ID 查询任务；
- PDF 转换器只处理当前报告使用的基础 Markdown，不支持复杂表格和图片；
- 扫描版 PDF 仍然需要 OCR；
- 法规库仍为 10 条教学样例，不是权威全量数据库。

## 9. 面试可能追问

问题：“FastAPI BackgroundTasks 算真正的异步任务队列吗？”

回答要点：它能让响应先返回，再在线程池中执行同步函数，适合单机 MVP；但任务与 Web 进程同生命周期，没有持久化队列、确认机制和跨实例调度。生产环境应使用 Celery/RQ 等，并把任务状态保留在数据库。

问题：“为什么前端和后端都校验文件？”

回答要点：前端校验提供及时反馈，不能作为安全边界，因为调用者可以绕过浏览器直接请求 API。后端必须独立校验大小、扩展名、MIME、内容可解析性和超时。

问题：“为什么不直接把 PDF 存服务器？”

回答要点：当前报告可由已持久化 Markdown 确定性生成，按需生成减少重复文件、清理任务和磁盘占用。大规模场景可生成后存对象存储，并用内容哈希避免重复。

问题：“轮询、SSE 和 WebSocket 怎么选？”

回答要点：低频单向状态更新使用轮询最简单可靠；SSE 适合服务器单向事件流；WebSocket 适合高频双向交互。当前 1.5 秒轮询满足演示体验且部署成本最低。

## 10. 本次简历描述是否需要更新

需要。可以在已有项目条目中补充：

> 使用 React、TypeScript 与 Vite 构建法律 Agent 交互界面，将同步 LangGraph 请求改造成基于 FastAPI BackgroundTasks 的任务资源，支持节点进度轮询、可追溯引用、Markdown/PDF 导出、10 MB 文件安全校验和结构化请求日志；编写前后端 Dockerfile 与 Compose 配置，后端 26 项自动测试和前端生产构建通过。

注意：在 Docker 实际构建验收完成前，不要在简历中声称“Docker 部署已验证”。

---

# 2026-07-22：pnpm 11 构建脚本白名单兼容

## 1. 本次解决的问题

用户安装 pnpm 11 后，运行前端时出现 `ERR_PNPM_IGNORED_BUILDS`。原因不是 React 代码失败，而是 pnpm 11 默认严格拒绝未经审核的依赖安装脚本，并且已经移除 pnpm 10 使用的 `onlyBuiltDependencies` 配置。

## 2. 用户可以看到的变化

项目的 `pnpm-workspace.yaml` 改用 pnpm 11 的 `allowBuilds`，明确只允许 `esbuild` 执行安装脚本。重新运行 `pnpm install` 后即可启动 Vite。

## 3. 新增或修改的文件

- `frontend/pnpm-workspace.yaml`：将旧白名单迁移为 `allowBuilds`；
- `README.md`：补充 pnpm 11 安装说明；
- `docs/LEARNING_JOURNAL.md`：追加本次兼容记录。

## 4. 核心实现原理

Vite 使用 esbuild 做开发期转换和依赖预构建。esbuild 的 npm 包需要在安装阶段选择当前操作系统对应的可执行文件，因此存在 install script。pnpm 11 的 `strictDepBuilds` 默认为 true，未在 `allowBuilds` 中明确审核的脚本会导致安装返回非零退出码。

项目没有开启 `dangerouslyAllowAllBuilds`，因为这会让现在和未来所有依赖都能执行脚本。当前采用最小权限白名单：

```yaml
allowBuilds:
  esbuild: true
```

## 5. 数据流转

```text
pnpm install
  → 读取 pnpm-workspace.yaml
  → 检查 esbuild 是否允许执行脚本
  → 执行 esbuild install.js
  → 安装 Windows x64 二进制
  → pnpm run dev 启动 Vite
```

## 6. 异常与安全处理

- 只允许项目实际需要的 esbuild；
- 不关闭所有依赖脚本检查；
- 不使用 `dangerouslyAllowAllBuilds=true`；
- 新依赖如果出现安装脚本，必须单独审核后才能加入白名单。

## 7. 验证方式

在 `frontend` 目录执行：

```powershell
pnpm install --registry=https://registry.npmmirror.com
pnpm run build
pnpm run dev
```

安装不应再出现 `ERR_PNPM_IGNORED_BUILDS`。

## 8. 已知限制和下一步

该配置针对 pnpm 11。锁文件继续保证依赖版本可复现；升级 pnpm 大版本时仍需检查官方迁移说明。

## 9. 面试可能追问

问题：“为什么不直接允许所有依赖执行安装脚本？”

回答要点：install/postinstall 在安装依赖时直接执行本机代码，是供应链攻击面。最小白名单能保留 esbuild 的必要功能，同时避免未来新增依赖自动获得脚本执行权限。

## 10. 本次简历描述是否需要更新

不需要。这属于前端依赖供应链安全和工具版本兼容细节，可在工程化问题中展开说明。

---

# 2026-07-22：棕金色文字对比度优化

## 1. 本次解决的问题

原页面把同一种浅金色同时用于深绿色背景和白色卡片背景。浅金色在深色背景上清晰，但放在白色或米白背景上对比度不足，栏目标题和部分提示文字不易阅读。

## 2. 用户可以看到的变化

- 深绿色首屏继续使用亮金色，保持品牌视觉；
- 白色和米白卡片上的栏目标题改成深棕色；
- 未核验引用标签使用更深的棕色；
- 免责声明文字加深并略微增大；
- 棕金色装饰线和圆点同步加深。

## 3. 新增或修改的文件

- `frontend/src/styles.css`：拆分深色背景与浅色背景的金色变量；
- `docs/LEARNING_JOURNAL.md`：追加本次可访问性记录。

## 4. 核心实现原理

颜色不能只按“品牌统一”复用，还必须根据背景分别设计。深色背景使用 `--gold-light`，浅色背景使用深棕色 `#704b10`，避免浅金色文字与白色背景亮度过于接近。

## 5. 页面样式流转

```text
深绿色首屏 → .eyebrow → --gold-light
白色功能卡片 → .kicker → #704b10
未核验标签 → 深棕文字 + 浅棕背景
免责声明 → 深棕灰文字 + 米白背景
```

## 6. 异常与安全处理

本次只调整 CSS 颜色，没有修改页面数据、接口、权限或用户输入处理。保留键盘焦点样式和 `prefers-reduced-motion` 设置。

## 7. 验证方式

执行 `pnpm run build`，确认 TypeScript 与 Vite 生产构建通过。刷新开发页面后重点检查白色卡片上的“案件输入”“执行过程”“分析完成”和免责声明。

## 8. 已知限制和下一步

当前没有引入自动化无障碍扫描；第四周可增加 axe 或 Lighthouse 检查，并把文字对比度纳入前端验收。

## 9. 面试可能追问

问题：“为什么同一个品牌金色要定义亮色和深色两种？”

回答要点：品牌色的视觉语义可以一致，但可读性取决于前景与背景的相对亮度。深浅背景应使用不同色阶，避免为了形式统一牺牲可访问性。

## 10. 本次简历描述是否需要更新

不需要。它属于前端可访问性和视觉质量优化，可在页面设计取舍中说明。

# 2026-07-22：首屏背景层级修复

## 1. 现象

首页标题“让每一条法律分析”、说明文字、顶部品牌名和知识库状态原本使用白色字体，但页面实际显示成了米白色背景，导致白字与背景几乎没有对比度。

## 2. 根因

首屏深绿色渐变原来绘制在 `.app-shell::before` 伪元素上，同时给伪元素设置了负数 `z-index`。在浏览器的层叠上下文中，这个伪元素可能被放到页面根背景之后，因此深绿色背景没有显示；白色字体本身并不是问题。

## 3. 修复内容

1. 把深绿色渐变和金色光晕直接设置为 `.app-shell` 的多层背景，不再依赖负层级伪元素。
2. 使用 `isolation: isolate` 创建独立层叠上下文，避免装饰层逃到页面背景之后。
3. 将背景区域高度调整为 760px，使首屏说明文字和功能特点都位于深色背景上。
4. 明确让顶部栏、主体和页脚位于装饰字之上，保证文字与按钮可交互、可阅读。

## 4. 求职面试知识点

当元素“存在但看不见”时，不应只检查颜色，还要检查 CSS 层叠上下文。`position`、`z-index`、`transform`、`opacity` 和 `isolation` 都可能创建或改变层叠上下文。负数 `z-index` 尤其容易让伪元素落到父元素背景或页面根背景后面。对于页面主背景，直接使用容器的 `background` 通常比负层级伪元素更稳定；伪元素更适合承载水印等非核心装饰。

## 5. 自测步骤

1. 启动前端：`pnpm run dev`。
2. 打开首页并执行一次强制刷新（Windows：`Ctrl + F5`）。
3. 确认页面顶部到首屏功能特点区域显示深绿色渐变背景。
4. 确认品牌名、主标题第一行、说明文字、知识库状态和三个功能特点均能清晰阅读。
5. 确认工作台区域仍为浅色背景，上传、示例案件和分析按钮的布局没有变化。

---

# 2026-07-23：第四周——评测、工程质量与求职发布

## 1. 本次解决的问题

前三周已经形成可运行产品，但“效果好不好”主要依赖主观体验；测试还会读取本机 `.env`，在 Agent 用例中意外调用真实 DeepSeek；仓库也缺少 CI、技术决策和可直接使用的求职材料。第四周把项目从功能演示推进为有数据、有质量门禁、有公开说明的求职作品。

## 2. 修改或新增的关键文件

- `eval/dataset.jsonl`：24 条合同/劳动争议均衡脱敏样例；
- `eval/metrics.py`、`eval/run_eval.py`：抽取、检索和系统评测；
- `eval/results/latest.json`、`latest.md`：机器与人工可读结果；
- `tests/test_fourth_week.py`：评测数据、安全输入和数据库锁测试；
- `scripts/run_self_test.py`：测试前强制离线并清除模型 Key；
- `app/tasks.py`：SQLite 锁有限退避重试和失败落库；
- `app/schemas.py`、`app/main.py`：返回实际执行引擎与模型；
- `frontend/src/App.tsx`、`types.ts`、`styles.css`：显示 LLM、规则或降级标签；
- `pyproject.toml`、`requirements-dev.txt`：Ruff 与 mypy；
- `.github/workflows/ci.yml`：后端与前端 CI；
- `docs/decisions/`：6 份 ADR；
- `docs/DEMO_SCRIPT.md`、`docs/JOB_MATERIALS.md`：录制、简历和面试材料；
- `README.md`、`PRODUCT_SPEC.md`、`PROJECT_GOALS.md`、`SELF_TEST.md`：第四周发布说明。

## 3. 核心实现原理

评测数据为 JSONL，每条记录固定 case ID、脱敏案情、问题、期望案件类型、事实/焦点关键词和相关 article ID。检索指标只依赖排名与标注：Recall@5 衡量相关条文找回比例；MRR 关注首条相关结果的位置；Hit@K 判断前 K 条是否至少命中一次；Precision@5 衡量返回结果中相关条文比例。

评测器在内存 SQLite 中建表、导入同一份法规数据并固定 Top-K=5，避免污染业务数据库。默认运行关键词、哈希语义和哈希混合三组；在线 Embedding 必须显式传入 `--include-online`，否则标记 `skipped`，避免意外费用。

Ruff 负责格式和静态问题，mypy 检查核心 Python 类型，GitHub Actions 在无密钥 Ubuntu 环境重复执行质量门禁、测试、评测和前端构建。

## 4. 请求与数据如何流转

```text
dataset.jsonl
  → 校验 case_id 与相关 article_id
  → 规则抽取 → 类型准确率/关键词覆盖率
  → 三种检索排名 → Recall@5/MRR/Hit@K/延迟
  → 离线 LangGraph → 成功率/平均与 P95 耗时
  → latest.json + latest.md
```

页面提交任务后，状态接口新增 `execution_engine` 和 `model`。后端根据最终持久化结果返回 `rules`、`llm` 或 `fallback`，前端直接展示标签。检索相似度不再被当作是否使用 Agent 的证据。

## 5. 评测发现与改进

首次运行时，案件类型规则准确率为 75%。错误主要来自“供应商、交付、承运、入职、经济补偿”等表达没有出现原始词表。扩充合同和劳动领域词后，同一数据集达到 100%；关键事实关键词覆盖率为 93.75%，争议焦点覆盖率仍有限，说明规则抽取无法替代更大规模人工评测和模型方案。

检索结果：关键词 Recall@5/MRR 为 1.0000/0.8000，哈希语义为 0.8403/0.7118，哈希混合为 0.8264/0.7361。当前只有 10 条教学法规，词面高度匹配，关键词优于弱哈希向量是合理结果。项目保留全部对照，不只展示最好的一组，也不把在线组写成已经完成。

## 6. 安全与异常处理

- 自测脚本在应用导入前强制离线、使用测试数据库并删除进程中的模型 Key；
- 损坏 PDF 返回 422，超大文件、MIME 伪装和恶意文件名继续受控；
- SQL/提示注入文本仅作为普通案件字符串处理，不进入命令或 SQL 拼接，也不会读取环境变量；
- 重复提交生成不同任务 ID，保留各自审计记录；
- SQLite 短暂锁使用 0.1/0.2 秒有限重试，超过上限后任务标记失败，不无限等待。

## 7. 测试与实际结果

本地实际结果：

- Ruff lint：通过；
- Ruff format check：通过；
- mypy：20 个核心源文件无问题；
- 后端：32 项测试通过，且没有真实模型 HTTP 请求；
- 离线工作流成功率：100%；
- 前端生产构建：188 个模块转换成功；
- GitHub Actions：工作流已创建，推送后以线上结果为准。

## 8. 已知限制

- 24 条数据规模小，且由单一项目作者构造；第二位标注者复核仍需人工完成；
- 关键词覆盖率不是严格语义评分；
- 当前没有独立 Embedding API，在线混合检索组未运行；
- 开发机没有 Docker，容器仍未实际构建；
- 演示脚本已经完成，但视频必须由项目作者录制并检查隐私。

## 9. 面试可能追问

问题：“为什么混合检索反而不如关键词？”

回答要点：数据只有 10 条且问题与法条词面高度匹配，哈希二元词向量不是强语义模型；混合权重会稀释关键词信号。对照实验的目的不是证明向量必胜，而是识别数据规模、模型和权重的适用条件。扩大法规库、接入真实 Embedding 后需要在同一评测集重新调权。

问题：“100% 案件类型准确率是否可信？”

回答要点：它只适用于 24 条作者构造的合同/劳动二分类数据，不能外推生产。文档同时保留首次 75% 基线、改进过程和单标注者偏差，后续需要盲测集与双人标注。

问题：“如何保证 CI 不产生模型费用？”

回答要点：测试入口在导入应用前覆盖 `OFFLINE_MODE=true`、使用 hash provider 并删除 Key；CI 不保存模型 Secret；网络相关逻辑使用 Fake/Mock 验证输出修复与超时降级。

## 10. 简历描述

可以使用 `docs/JOB_MATERIALS.md` 中的量化描述，但必须保留“24 条脱敏教学样例”范围。在线 Embedding、Docker 和演示视频在实际验收前不能写成已完成。

---

# 2026-07-23：GitHub Actions 首次云端验收

第四周提交 `d8d6ab8` 推送到 GitHub 后触发 `CI` 工作流，运行 ID 为 `29946002021`。`backend` Job 完成依赖安装、Ruff 格式检查、Ruff 静态检查、mypy、32 项后端测试和离线评测；`frontend` Job完成 pnpm 锁文件安装、TypeScript 检查和 Vite 构建。两个 Job 均返回 `success`。

这次验收证明项目不依赖开发机的 `.venv`、SQLite 运行库、Node modules 或真实模型 Key。CI 环境显式使用离线模式，因此不会产生 DeepSeek 或 Embedding 费用。后续每次推送 `main` 或创建 Pull Request 都会重新执行相同门禁。

面试追问：“本地测试通过为什么还需要 CI？”回答要点：本地可能隐式依赖缓存、环境变量或已安装软件；CI 在全新环境按仓库声明重建依赖，能够发现缺失文件、锁文件不一致、平台差异和测试偷偷读取本机密钥等问题。
