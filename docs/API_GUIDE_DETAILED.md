# 律镜 Legal Copilot Agent：逐接口含义与返回示例

本文档面向两类读者：一类是希望使用 Apifox 调试项目的开发者，另一类是希望通过项目准备 Python、FastAPI、Agent 与后端岗位面试的学习者。

文档以当前项目代码和 `docs/openapi.json` 为准。每个接口都说明业务含义、请求方法、参数、返回字段、成功示例、常见错误和下一步调用。

## 1. 阅读前先区分接口状态

| 状态 | 含义 | 当前能否调用 |
|---|---|---|
| `implemented` | 已写入 FastAPI 路由并经过自动测试 | 可以 |
| `planned` | 已在 OpenAPI 中提前设计，供后续开发保持契约稳定 | 不可以，当前通常返回 `404 Not Found` |

当前共定义 25 个接口：21 个已实现，4 个处于规划阶段。规划接口中的响应 JSON 是“预期契约示例”，不是当前服务真实返回。

## 2. 基础信息

### 2.1 服务地址

```text
http://127.0.0.1:8000
```

常用页面：

- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`
- Apifox 导入文件：`docs/openapi.json`

建议在 Apifox 中创建本地环境变量：

```text
baseUrl = http://127.0.0.1:8000
```

之后把接口前缀写成 `{{baseUrl}}`。

### 2.2 两种请求体

| Content-Type | 使用接口 | Apifox 填写位置 |
|---|---|---|
| `application/json` | 法规搜索、知识库单条新增、追问回答、报告审批、评测 | Body → JSON |
| `multipart/form-data` | 案件分析、Agent 任务、批量导入 | Body → form-data；文件字段选择 File |

不要手工填写 multipart 的 `Content-Type` 边界，交给 Apifox 自动生成。

### 2.3 ID 之间的关系

- `article_id`：法规表中一条法规的整数主键。
- `run_id`：一次案件分析任务的整数主键。
- `job_id`：一次知识库批量导入任务的 UUID。
- `evaluation_id`：一次离线评测任务的 UUID。

`run_id` 是 Agent 调用链的核心：创建任务后，用同一个 `run_id` 查询状态、引用和报告。

## 3. 推荐调用流程

### 3.1 最小验证流程

```text
GET /health
  → POST /api/v1/articles/search
  → GET /api/v1/articles/{article_id}
```

它用于确认服务、数据库、法规检索和法规回查都正常。

### 3.2 完整 Agent 流程

```text
POST /api/v1/runs
  → 保存 run_id
GET /api/v1/runs/{run_id}
  → 查看 status、progress、traces
  → waiting_for_approval 时读取 pending-action 并提交 approvals
GET /api/v1/runs/{run_id}/citations
  → 检查引用及审核状态
GET /api/v1/runs/{run_id}/report
  → 读取当前草稿或已批准报告
GET /api/v1/runs/{run_id}/export
  → 只下载已批准版本
```

第三周版本已经使用 FastAPI 后台任务执行工作流。创建接口立即返回 `queued`，前端每 1.5 秒轮询状态接口；生产级多实例部署时应进一步迁移到 Celery、RQ 或其他持久任务队列。

---

# 4. 已实现接口

## 4.1 GET `/health`：服务健康检查

### 具体含义

用于判断 API 进程能否响应、数据库能否读取，以及当前知识库有多少条法规。它适合放在启动验收、部署探针和故障排查的第一步。

### 请求

无路径参数、查询参数和请求体。

```http
GET {{baseUrl}}/health
```

### 成功返回：200

```json
{
  "status": "ok",
  "article_count": 37
}
```

字段含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `status` | string | `ok` 表示服务和本次检查正常 |
| `article_count` | integer | 数据库中当前法规条文数量；全新数据库首次启动为 36 条 JSONL 教学数据加 1 条历史版本演示数据 |

`article_count` 大于 0 说明样例法规已经初始化。它不是业务结果总数，也不是 Agent 任务数。

### 常见问题

- 浏览器访问 `/` 返回 `{"detail":"Not Found"}` 是正常的，因为项目没有定义首页。
- 应访问 `/health` 或 `/docs`。
- 无法连接通常表示服务未启动、端口被占用或运行配置的工作目录不正确。

### 下一步

调用法规搜索接口，验证数据库内容是否真正可检索。

## 4.2 GET `/api/v1/examples/questions/random`：随机生成案件问题示例

### 具体含义

从人工设计的案件模板和变量池随机组合自然语言问题，供用户快速体验离线分析或智能 Agent。接口本身不调用 LLM，因此没有模型费用，也不会因为模型服务不可用而失效。

`brief` 适合快速试接口；`detailed` 会生成多句完整案情，包含时间、人物、交易或劳动关系、事件经过、损害结果、已有证据、对方态度和具体诉求，更适合验证 Agent 的案件摘要和事实抽取能力。

### 请求

```http
GET {{baseUrl}}/api/v1/examples/questions/random?count=3&category=食品安全&detail_level=detailed
```

| 参数 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `count` | 否 | 1～10，默认 3 | 返回多少个问题 |
| `category` | 否 | 必须是响应中 `available_categories` 的值 | 限定案件分类；不传时从全部分类生成 |
| `detail_level` | 否 | `brief` 或 `detailed`，默认 `brief` | 一句话问题或包含背景、证据和诉求的详细案情 |

### 成功返回：200

```json
{
  "count": 2,
  "requested_category": "食品安全",
  "requested_detail_level": "detailed",
  "available_categories": [
    "劳动争议",
    "合同纠纷",
    "食品安全",
    "消费者权益"
  ],
  "examples": [
    {
      "example_id": "e54f0d96ce18",
      "category": "食品安全",
      "detail_level": "detailed",
      "question": "2026年4月12日晚上，王女士通过外卖平台在一家餐馆购买海鲜套餐，支付128元。食用后约两小时，王女士出现持续呕吐、腹泻和发热并前往医院，诊断为急性胃肠炎，已经产生医疗费和误工损失。王女士保留了订单、小票、食品照片、剩余食品、病历和付款记录，但商家只愿退还餐费，不认可食品与身体不适之间存在关系。王女士想了解商家是否应承担赔偿责任、还需要补充哪些证据，以及可以主张哪些费用。"
    },
    {
      "example_id": "3a49ce8ec109",
      "category": "食品安全",
      "detail_level": "detailed",
      "question": "2026年5月3日晚上，李女士在线下门店购买熟食，食用后当天夜间出现腹痛、恶心和脱水并就医……"
    }
  ]
}
```

`example_id` 由分类和最终问题计算得到，同一个问题拥有稳定标识。同一次响应保证问题不重复，但两次请求可能随机到相同问题。`detail_level` 会同时出现在顶层请求回显和每个示例中，方便前端确认实际生成模式。

### 常见错误

- `count=0` 或大于 10：返回 422；
- 分类不存在：返回 422，`detail` 会列出可选分类；
- `detail_level` 不是 `brief/detailed`：返回 422；
- 前端请求失败：保留三个内置兜底示例，不影响用户手工输入问题。

### 下一步

把任意 `question` 作为 `POST /api/v1/runs` 的问题字段提交；随机接口只提供输入，不会自动创建 Agent 任务。

## 4.3 POST `/api/v1/articles/search`：搜索相关法规

### 具体含义

把自然语言法律问题转换为检索请求，在法规知识库中返回相关度最高的 Top-K 条文。当前实现结合关键词和语义分数：`OFFLINE_MODE=true` 或 `EMBEDDING_PROVIDER=hash` 时使用本地哈希；配置 `openai-compatible` 时使用真正的在线 Embedding。在线配置错误、认证失败、超时或响应异常时，当前请求会安全降级到哈希检索。

第七周增加时间约束：传入 `as_of_date` 时，先筛选该日有效的法规版本，再进行关键词和向量召回；留空时使用服务器当前日期。有效区间是 `[effective_from, effective_to)`，即生效日包含、失效日不包含。

### 请求

Content-Type：`application/json`

```json
{
  "query": "迟延履行经催告仍未履行，可以解除合同吗",
  "limit": 5,
  "as_of_date": "2020-12-31"
}
```

| 字段 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `query` | 是 | 至少 2 个字符 | 用户问题或检索关键词 |
| `limit` | 否 | 1～20，默认 5 | 最多返回多少条法规 |
| `as_of_date` | 否 | `YYYY-MM-DD` | 法规适用时点；留空按当前日期 |

### 成功返回：200

```json
[
  {
    "article_id": 242,
    "law_name": "中华人民共和国合同法",
    "article_number": "第九十四条",
    "excerpt": "当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行的，当事人可以解除合同。",
    "source": "国家法律法规数据库历史文本；教学节选",
    "score": 0.6432,
    "keyword_score": 0.5714,
    "semantic_score": 0.6819,
    "law_id": 7,
    "law_version_id": 8,
    "version_label": "1999年施行版本",
    "effect_status": "repealed",
    "effective_from": "1999-10-01",
    "effective_to": "2021-01-01"
  }
]
```

| 字段 | 含义 |
|---|---|
| `article_id` | 后续回查法规全文使用的 ID |
| `law_name` | 法律、法规或司法解释名称 |
| `article_number` | 条文编号 |
| `excerpt` | 用于列表展示的法规摘要或原文片段 |
| `source` | 数据来源说明；正式项目应替换为权威来源 |
| `score` | 综合相关度分数，用于最终排序 |
| `keyword_score` | 关键词匹配分数 |
| `semantic_score` | 语义相似度分数 |
| `law_id` | 法规实体 ID；用于区分“哪一部法律” |
| `law_version_id` | 精确法规版本 ID；报告快照和引用记录保存此值 |
| `version_label` | 版本名称，例如“1999年施行版本” |
| `effect_status` | `effective`、`amended`、`repealed` 或兼容旧数据的 `legacy` |
| `effective_from` | 版本开始生效日期 |
| `effective_to` | 版本失效日期；`null` 表示没有登记结束日期 |

分数只用于当前候选集内比较，不能解释为“法律结论有 64.32% 正确”。

响应头会明确告诉调用方本次实际使用的向量引擎：

```text
X-Embedding-Provider: hash
X-Embedding-Model: chinese-bigram-sha256-v1
X-Law-As-Of-Date: 2020-12-31
```

在线调用成功时，响应头会变为 `.env` 配置的 provider/model；如果仍显示 `hash`，说明处于离线模式或在线服务已经降级。不能通过相似度分数判断是否调用了在线模型。

### 参数错误：422

例如 `query` 只有一个字符：

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "query"],
      "msg": "String should have at least 2 characters",
      "input": "合"
    }
  ]
}
```

### 下一步

从返回数组中取出 `article_id`，调用法规详情接口核对完整原文。

## 4.4 GET `/api/v1/articles/{article_id}`：获取法规条文详情

### 具体含义

根据搜索结果中的 `article_id` 回查知识库原文。它解决“报告引用是否能够追溯”的问题，是引用可核验设计的一部分。

### 请求

```http
GET {{baseUrl}}/api/v1/articles/3
```

| 参数 | 位置 | 类型 | 含义 |
|---|---|---|---|
| `article_id` | path | integer | 法规条文主键，必须替换为真实 ID |

### 成功返回：200

```json
{
  "article_id": 3,
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百七十七条",
  "content": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
  "source": "项目内置教学样例",
  "law_id": 7,
  "law_version_id": 8,
  "version_label": "2020年通过（2021年施行）",
  "effect_status": "effective",
  "effective_from": "2021-01-01",
  "effective_to": null
}
```

`content` 是完整存储内容，而搜索接口的 `excerpt` 适合结果列表展示。

### 资源不存在：404

```json
{
  "detail": "未找到法规条文"
}
```

排查方法：先执行搜索，不要猜测 `article_id`。

## 4.5 POST `/api/v1/cases`：同步分析案件（兼容接口）

### 具体含义

这是第一周保留的同步接口。它接收用户问题和可选案件文件，在一次 HTTP 请求中完成文本解析、案件要素提取和法规检索，并返回简化结果。

新功能建议优先调用 `/api/v1/runs`，因为后者能查看节点轨迹、引用审核和完整报告。

### Apifox 请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 示例 |
|---|---|---|---|
| `question` | Text | 是 | `供应商收款后未按合同交货，我能否解除合同并要求赔偿？` |
| `as_of_date` | Text | 否 | `2020-12-31`；留空按当前日期 |
| `file` | File | 否 | `contract.txt`、`contract.docx` 或 `contract.pdf` |

只填写问题也可以调用。

### 成功返回：201

```json
{
  "run_id": 21,
  "as_of_date": "2020-12-31",
  "facts": {
    "case_type": "合同纠纷",
    "parties": ["供应商", "采购方"],
    "key_facts": ["供应商收款后未按合同交货"],
    "claims": ["解除合同", "要求赔偿损失"],
    "dispute_focuses": ["是否构成违约", "是否达到合同解除条件"],
    "confidence": 0.82,
    "missing_information": ["合同约定的交货期限", "催告和沟通记录"],
    "questions_for_user": ["合同约定的交货日期是什么？", "是否已经书面催告供应商？"]
  },
  "citations": [
    {
      "article_id": 242,
      "law_name": "中华人民共和国合同法",
      "article_number": "第九十四条",
      "excerpt": "当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行的，当事人可以解除合同。",
      "source": "国家法律法规数据库历史文本；教学节选",
      "score": 0.6432,
      "keyword_score": 0.5714,
      "semantic_score": 0.6819,
      "law_id": 1,
      "law_version_id": 1,
      "version_label": "1999年施行版本",
      "effect_status": "repealed",
      "effective_from": "1999-10-01",
      "effective_to": "2021-01-01"
    }
  ],
  "notice": "本结果仅用于技术演示，不构成法律意见。"
}
```

`facts` 各字段：

| 字段 | 含义 |
|---|---|
| `case_type` | 识别出的案件类别，如合同纠纷、劳动争议；服务保证该字段不是空字符串。LLM 连续两次返回空值时会改用规则识别 |
| `parties` | 文本中出现的主要当事人角色 |
| `key_facts` | 对结论可能有影响的关键事实 |
| `claims` | 用户提出或可能提出的诉求 |
| `dispute_focuses` | 双方最需要判断的法律争点 |
| `confidence` | 要素提取置信度，不代表胜诉概率 |
| `missing_information` | 当前材料缺少的重要事实或证据 |
| `questions_for_user` | 系统建议进一步向用户询问的问题 |

### 常见错误

不支持的文件类型返回 415：

```json
{
  "detail": "不支持的文件类型，请上传 .txt、.docx 或 .pdf 文件"
}
```

问题缺失或长度不足返回 422。扫描版 PDF 可能提取不到文本，因为当前版本没有 OCR。

## 4.6 POST `/api/v1/runs`：创建 Agent 分析任务

### 具体含义

这是项目的核心入口。请求会执行完整 LangGraph 工作流：案件要素分析 → 按日期筛选有效法规版本 → 混合检索 → 引用审核 → 报告生成 → 人工审批，并持久化运行状态和节点轨迹。

### Apifox 请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 默认值 | 含义 |
|---|---|---|---|---|
| `question` | Text | 是 | 无 | 用户的法律问题，2～5000 字符 |
| `mode` | Text | 否 | `offline` | `offline` 或 `agent` |
| `as_of_date` | Text | 否 | 当前日期 | 案件发生日，格式 `YYYY-MM-DD` |
| `file` | File | 否 | 无 | TXT、DOCX 或 PDF 案件材料 |

示例：

```text
question = 供应商收款后未按合同交货，我能否解除合同并要求赔偿？
mode = offline
as_of_date = 2020-12-31
```

模式区别：

- `offline`：规则分析、本地哈希向量和模板报告，不需要网络或 API Key。
- `agent`：当 `OFFLINE_MODE=false` 且 LLM 配置完整时请求模型；不可用时进行安全降级。

### 成功返回：202

```json
{
  "run_id": 31,
  "status": "queued",
  "as_of_date": "2020-12-31",
  "status_url": "/api/v1/runs/31",
  "report_url": "/api/v1/runs/31/report"
}
```

| 字段 | 含义 |
|---|---|
| `run_id` | 本次任务 ID，后续三个查询接口都使用它 |
| `status` | 创建响应固定为 `queued`，后续通过状态接口观察变化 |
| `as_of_date` | 用户指定的法规检索日期；未指定时为 `null`，检索仍按当前日期 |
| `status_url` | 状态查询相对地址 |
| `report_url` | 报告查询相对地址 |

为什么使用 202：服务器已经接受任务，但分析仍在后台执行。调用方不应等待创建请求直接返回报告，而应保存 `run_id` 并轮询状态接口。

### 常见错误

- 415：文件扩展名不受支持。
- 422：问题太短、过长，或 `mode` 不是 `offline/agent`。
- 429：规划中的并发或频率限制；当前不一定触发。

### 下一步

保存 `run_id`，先调用任务状态接口，不要直接假定报告已经可以读取。

## 4.7 GET `/api/v1/runs/{run_id}`：查询任务状态和节点轨迹

### 具体含义

用于观察 Agent 当前执行到哪个节点、整体进度、重试次数、提取结果和错误信息。它也是展示“Agent 并非单次黑盒调用”的关键接口。

### 请求

```http
GET {{baseUrl}}/api/v1/runs/31
```

### 成功返回：200

```json
{
  "run_id": 31,
  "status": "completed",
  "current_node": "completed",
  "progress": 100,
  "retry_count": 0,
  "clarification_round": 1,
  "state_version": 3,
  "pending_action_url": null,
  "mode": "offline",
  "as_of_date": "2020-12-31",
  "execution_engine": "rules",
  "model": "offline-template",
  "facts": {
    "case_type": "合同纠纷",
    "parties": ["供应商", "采购方"],
    "key_facts": ["供应商收款后未交货"],
    "claims": ["解除合同", "赔偿损失"],
    "dispute_focuses": ["违约责任", "合同解除条件"],
    "confidence": 0.82,
    "missing_information": ["交货期限", "催告记录"],
    "questions_for_user": ["是否已经书面催告？"]
  },
  "traces": [
    {
      "node": "analyze_case",
      "status": "completed",
      "duration_ms": 3,
      "action_summary": "完成案件要素提取",
      "error_code": null
    },
    {
      "node": "retrieve_laws",
      "status": "completed",
      "duration_ms": 8,
      "action_summary": "检索候选法规",
      "error_code": null
    },
    {
      "node": "review_citations",
      "status": "completed",
      "duration_ms": 1,
      "action_summary": "完成引用审核",
      "error_code": null
    },
    {
      "node": "write_report",
      "status": "completed",
      "duration_ms": 2,
      "action_summary": "生成结构化报告",
      "error_code": null
    }
  ],
  "error_code": null,
  "error_message": null
}
```

常见状态：`queued`、`parsing`、`analyzing`、`waiting_for_user`、`resuming`、`retrieving`、`reviewing`、`writing`、`completed`、`failed`。

- `waiting_for_user`：工作流已经持久化并暂停，必须查询 `pending_action_url`；
- `resuming`：回答已经保存，后台任务正在恢复同一个 LangGraph thread；
- `clarification_round`：当前或已经完成的追问轮次，最大为 3；
- `state_version`：并发控制版本；提交回答时必须原样带回；
- `pending_action_url`：只有等待回答时返回待办地址，其他状态为 `null`。

执行来源字段：

- `execution_engine=pending`：尚未完成首次要素抽取，暂时不能判断执行引擎；
- `execution_engine=rules`：离线规则和模板完成，未调用模型；
- `execution_engine=llm`：至少成功使用了 `model` 指定的模型；
- `execution_engine=fallback`：用户选择 Agent，但模型不可用或配置关闭，最终由离线方案完成；
- `model`：实际记录的模型名；离线完成通常为 `offline-template`。
- `retrieve_laws` 轨迹中的 `provider` 表示该节点最终使用的向量方案。在线 Embedding 会先重试一次；若最终显示 `hash`，`action_summary` 会包含具体回退原因。
- `retrieve_laws` 轨迹同时记录实际法规适用日期；先做日期过滤，再计算相关度。
- `analyze_case` 轨迹中的 `source=llm_enriched` 表示模型返回“未识别”后，服务保留模型抽取字段并用本地分类器补全了案件类型。

判断是否真的使用 Agent 应读取 `execution_engine` 和 `model`，不能根据检索相似度判断。相同问题使用相同法规库时，两种模式可能得到相同检索分数。

`traces` 是公开的可观测轨迹：

- `node`：节点名称。
- `status`：节点执行状态。
- `duration_ms`：节点耗时，单位毫秒。
- `action_summary`：适合用户阅读的动作摘要。
- `error_code`：节点失败时的稳定错误标识。

失败任务会通过 `error_code` 和 `error_message` 给出原因，不应只依赖 HTTP 状态判断 Agent 是否成功。

### 不存在：404

```json
{
  "detail": "未找到指定任务"
}
```

## 4.8 GET `/api/v1/runs/{run_id}/pending-action`：读取当前人工待办

### 具体含义

当状态为 `waiting_for_user` 时，这个接口返回 Agent 当前缺少的信息和问题编号；当状态为 `waiting_for_approval` 时，返回待审批报告版本和允许动作。调用方不能自行编造 action ID。

该接口也可以在页面刷新或后端重启后调用。问题和 LangGraph checkpoint 都已持久化，不依赖原浏览器页面或原 Python 进程内存。

### 请求

```http
GET {{baseUrl}}/api/v1/runs/31/pending-action
```

### 有待办时：200

```json
{
  "run_id": 31,
  "status": "waiting_for_user",
  "state_version": 1,
  "action": {
    "action_id": 7,
    "type": "clarification",
    "round": 1,
    "max_rounds": 3,
    "questions": [
      {
        "question_id": "r1-q1",
        "prompt": "合同约定的交货日期或履行期限是什么？如果没有约定，可以回答“暂不清楚”。",
        "missing_field": "约定交货日期或履行期限",
        "required": true
      }
    ]
  }
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `state_version` | 当前任务版本，提交回答时填入 `expected_state_version` |
| `action_id` | 当前待办记录 ID，前端用它生成稳定幂等键 |
| `round` | 当前第几轮追问 |
| `max_rounds` | 最大追问轮数，当前默认 3 |
| `question_id` | 回答与问题的关联键 |
| `missing_field` | Agent 认为缺少的事实；可能为 `null` |
| `required` | 本轮是否必须回答；当前问题均为 `true` |

审批待办示例：

```json
{
  "run_id": 31,
  "status": "waiting_for_approval",
  "state_version": 3,
  "action": {
    "action_id": 12,
    "type": "approval",
    "report_version": 2,
    "report_version_id": 18,
    "title": "合同纠纷法律分析报告",
    "change_summary": "根据审批意见生成第 2 版",
    "allowed_actions": ["approve", "request_changes", "reject"]
  }
}
```

### 当前无待办：200

接口仍返回任务状态，但 `action` 为 `null`：

```json
{
  "run_id": 31,
  "status": "completed",
  "state_version": 3,
  "action": null
}
```

### 常见错误

- 404：`run_id` 不存在。

## 4.9 POST `/api/v1/runs/{run_id}/clarifications`：提交回答并恢复 Agent

### 具体含义

保存本轮全部回答，把任务从 `waiting_for_user` 原子地改为 `resuming`，然后使用 LangGraph `Command(resume=...)` 恢复原 checkpoint。恢复不会创建新任务，后续仍查询同一个 `run_id`。

### Apifox 请求

Headers：

| Key | 必填 | 示例 | 含义 |
|---|---|---|---|
| `Content-Type` | 是 | `application/json` | JSON 请求体 |
| `Idempotency-Key` | 是 | `run-31-round-1-answer` | 8–200 字符；本轮重试必须复用同一个值 |

Body：

```json
{
  "expected_state_version": 1,
  "answers": [
    {
      "question_id": "r1-q1",
      "answer": "合同约定交货日期为2026年6月30日。"
    }
  ]
}
```

| 字段 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `expected_state_version` | 是 | 大于等于 0 | 必须等于待办接口返回的版本 |
| `answers` | 是 | 1–5 项 | 必须完整覆盖当前问题，不能重复 |
| `question_id` | 是 | 1–100 字符 | 从待办接口复制 |
| `answer` | 是 | 1–5000 字符 | 用户知道的事实；不了解可以写“暂不清楚” |

### 首次受理：202

```json
{
  "run_id": 31,
  "status": "resuming",
  "state_version": 2,
  "replayed": false,
  "status_url": "/api/v1/runs/31",
  "message": "回答已保存，Agent 正在从持久化 checkpoint 恢复。"
}
```

202 表示回答已经受理，报告不一定已经完成。继续轮询 `status_url`；可能进入下一轮 `waiting_for_user`，也可能完成。

### 相同幂等键重放：202

```json
{
  "run_id": 31,
  "status": "completed",
  "state_version": 3,
  "replayed": true,
  "status_url": "/api/v1/runs/31",
  "message": "相同幂等键的回答已经受理，本次未重复恢复工作流。"
}
```

网络超时后重试时必须复用原幂等键。`replayed=true` 说明服务识别到重复请求，没有再次合并回答、生成引用或报告。

### 常见错误

- 404：任务不存在；
- 409：任务不在等待回答状态；
- 409：`expected_state_version` 已过期，说明另一个页面已经提交；
- 422：缺少 `Idempotency-Key`、幂等键太短、回答为空、漏答或包含未知 `question_id`。

## 4.9A POST `/api/v1/runs/{run_id}/approvals`：审批报告并恢复 Agent

### 具体含义

报告草稿完成后，工作流停在 `approve_report` interrupt，任务状态为 `waiting_for_approval`。本接口保存人工决定，并从同一个 LangGraph checkpoint 恢复：

- `approve`：批准当前版本，任务进入 `completed`；
- `request_changes`：旧版本保留为 `superseded`，生成下一版本后再次等待审批；
- `reject`：终止发布，任务进入 `rejected`。

### Apifox 请求

```http
POST {{baseUrl}}/api/v1/runs/31/approvals
Content-Type: application/json
Idempotency-Key: run-31-version-1-approve
```

```json
{
  "expected_state_version": 1,
  "action": "approve",
  "comment": "案件事实、引用和风险提示已经核对。",
  "reviewer": "张审核"
}
```

| 字段 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `expected_state_version` | 是 | 大于等于 0 | 必须复制待办接口返回值 |
| `action` | 是 | `approve` / `request_changes` / `reject` | 审批决定 |
| `comment` | 修改/驳回时必填 | 最长 5000 字符 | 审批意见 |
| `reviewer` | 否 | 1–100 字符 | 本地演示审核人，默认“本地审核人” |

### 成功返回：202

```json
{
  "run_id": 31,
  "action": "request_changes",
  "status": "revising",
  "state_version": 2,
  "report_version": 1,
  "replayed": false,
  "status_url": "/api/v1/runs/31",
  "message": "修改意见已保存，Agent 正在生成新版本。"
}
```

继续轮询 `status_url`。要求修改后会出现新的审批待办；批准后为 `completed`；驳回后为 `rejected`。

### 常见错误

- 409：任务不在 `waiting_for_approval`；
- 409：状态版本过期或审批已经被另一个页面处理；
- 422：缺少幂等键，或修改/驳回时没有填写意见；
- 相同幂等键重试：仍返回 202，`replayed=true`，不会重复生成版本。

## 4.9B GET `/api/v1/runs/{run_id}/report-versions`：读取报告版本历史

### 具体含义

按版本号倒序返回当前任务全部报告版本。`draft` 表示待审批，`superseded` 表示已被修改版替代，`approved` 表示最终发布版，`rejected` 表示被驳回。

```http
GET {{baseUrl}}/api/v1/runs/31/report-versions
```

```json
[
  {
    "version_number": 2,
    "status": "approved",
    "title": "合同纠纷法律分析报告",
    "change_summary": "根据审批意见生成第 2 版：区分合同解除与损失赔偿",
    "created_at": "2026-07-31T15:00:00",
    "approved_at": "2026-07-31T15:01:00"
  },
  {
    "version_number": 1,
    "status": "superseded",
    "title": "合同纠纷法律分析报告",
    "change_summary": "Agent 生成初始报告草稿",
    "created_at": "2026-07-31T14:58:00",
    "approved_at": null
  }
]
```

## 4.9C GET `/api/v1/runs/{run_id}/report-versions/{version_number}`：读取版本内容和差异

### 具体含义

返回指定版本的完整 Markdown、事实快照、引用快照，以及相对上一版本的 unified diff。第一版没有上一版，因此 `diff_from_previous` 为空字符串。

```http
GET {{baseUrl}}/api/v1/runs/31/report-versions/2
```

```json
{
  "version_number": 2,
  "status": "approved",
  "title": "合同纠纷法律分析报告",
  "change_summary": "根据审批意见生成第 2 版",
  "created_at": "2026-07-31T15:00:00",
  "approved_at": "2026-07-31T15:01:00",
  "markdown": "# 合同纠纷法律分析报告\n……",
  "facts": {
    "case_type": "合同纠纷",
    "parties": [],
    "key_facts": ["供应商逾期交货"],
    "claims": ["解除合同"],
    "dispute_focuses": ["违约责任"],
    "confidence": null,
    "missing_information": [],
    "questions_for_user": []
  },
  "citations": [],
  "diff_from_previous": "--- v1\n+++ v2\n@@ ……"
}
```

不存在的任务或版本返回 404。

## 4.10 POST `/api/v1/runs/{run_id}/retry`：重试失败任务

### 具体含义

只允许对 `failed` 状态的任务发起新尝试。重试不会覆盖原任务，而是创建新的 `run_id`，从而保留失败现场和审计记录。

### 请求

```http
POST {{baseUrl}}/api/v1/runs/31/retry
```

不需要请求体。

### 成功返回：202

```json
{
  "run_id": 32,
  "status": "queued",
  "status_url": "/api/v1/runs/32",
  "report_url": "/api/v1/runs/32/report"
}
```

注意返回的是新任务 `32`，后续查询必须换成新的 ID。

### 状态不允许：409

如果原任务已经完成：

```json
{
  "detail": "只有失败任务可以重试"
}
```

### 不存在：404

```json
{
  "detail": "未找到指定任务"
}
```

## 4.11 GET `/api/v1/runs/{run_id}/citations`：获取任务引用及审核结果

### 具体含义

返回 Agent 检索到的候选法规及其审核状态。它把“模型生成内容”和“证据来源”拆开，让前端或人工审核者能够单独检查每条引用。

### 请求

```http
GET {{baseUrl}}/api/v1/runs/31/citations
```

### 成功返回：200

```json
[
  {
    "article_id": 3,
    "law_name": "中华人民共和国民法典",
    "article_number": "第五百七十七条",
    "excerpt": "当事人一方不履行合同义务……应当承担违约责任。",
    "source": "项目内置教学样例",
    "score": 0.6432,
    "keyword_score": 0.5714,
    "semantic_score": 0.6819,
    "law_id": 7,
    "law_version_id": 8,
    "version_label": "2020年通过（2021年施行）",
    "effect_status": "effective",
    "effective_from": "2021-01-01",
    "effective_to": null,
    "review_status": "verified",
    "review_reason": "条文内容与案件中的合同不履行问题相关",
    "verified": true
  }
]
```

新增审核字段：

| 字段 | 含义 |
|---|---|
| `review_status` | `pending`、`verified`、`rejected` 或 `low_confidence` |
| `review_reason` | 为什么接受、拒绝或降为低置信度 |
| `verified` | 是否通过当前自动审核；不等于权威人工核验 |

版本字段来自检索时选中的 `law_versions` 记录。即使 `effect_status=repealed`，如果用户查询的是该版本废止前的历史日期，它仍可能是“该历史时点有效”的正确候选；前端会同时显示废止状态和适用区间，避免误解为现行法。

实际产品中，只有 `verified=true` 的引用才应进入最终法律分析正文。仍应通过 `article_id` 回查原文和权威来源。

### 不存在：404

```json
{
  "detail": "未找到指定任务"
}
```

## 4.12 GET `/api/v1/runs/{run_id}/report`：获取结构化分析报告

### 具体含义

草稿生成后即可返回当前 Markdown、结构化案件事实、证据缺口、引用和审批状态。只有 `is_final=true` 才表示当前版本已经人工批准。

### 请求

```http
GET {{baseUrl}}/api/v1/runs/31/report
```

### 成功返回：200

```json
{
  "run_id": 31,
  "as_of_date": "2020-12-31",
  "version_number": 2,
  "approval_status": "approved",
  "is_final": true,
  "title": "合同纠纷法律分析报告",
  "markdown": "# 合同纠纷法律分析报告\n\n## 一、案件要素\n供应商收款后未按合同交货……\n\n## 二、相关法规\n《中华人民共和国民法典》第五百七十七条……",
  "facts": {
    "case_type": "合同纠纷",
    "parties": ["供应商", "采购方"],
    "key_facts": ["供应商收款后未交货"],
    "claims": ["解除合同", "赔偿损失"],
    "dispute_focuses": ["违约责任", "合同解除条件"],
    "confidence": 0.82,
    "missing_information": ["交货期限", "催告记录"],
    "questions_for_user": ["是否已经书面催告？"]
  },
  "evidence_gaps": ["合同原件", "付款凭证", "催告送达记录"],
  "citations": [
    {
      "article_id": 242,
      "law_name": "中华人民共和国合同法",
      "article_number": "第九十四条",
      "excerpt": "当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行的，当事人可以解除合同。",
      "source": "国家法律法规数据库历史文本；教学节选",
      "score": 0.6432,
      "keyword_score": 0.5714,
      "semantic_score": 0.6819,
      "law_id": 1,
      "law_version_id": 1,
      "version_label": "1999年施行版本",
      "effect_status": "repealed",
      "effective_from": "1999-10-01",
      "effective_to": "2021-01-01",
      "review_status": "verified",
      "review_reason": "与合同不履行问题相关",
      "verified": true
    }
  ],
  "notice": "本结果仅用于技术演示，不构成法律意见。",
  "model": "offline-template"
}
```

重要字段：

| 字段 | 含义 |
|---|---|
| `version_number` | 当前返回的报告版本 |
| `as_of_date` | 本次任务指定的案件日期；为空表示按当前日期检索 |
| `approval_status` | `draft`、`approved`、`superseded` 或 `rejected` |
| `is_final` | 是否已经人工批准并可以最终导出 |
| `markdown` | 可以直接展示或保存的完整报告文本 |
| `evidence_gaps` | 作出更可靠判断前仍需补充的证据 |
| `model` | 实际使用的模型或离线模板名称 |

### 报告未就绪：409

```json
{
  "detail": "任务尚未完成，暂时无法获取报告"
}
```

处理方式：先查 `/runs/{run_id}`。如果状态是 `failed`，读取错误信息并决定是否调用 retry。

---

# 5. 第三周新增与后续规划接口

本章的报告导出接口已在第三周实现；知识库管理和离线评测接口仍是后续规划。只有标记为规划的接口当前请求时通常返回：

```json
{
  "detail": "Not Found"
}
```

## 5.1 GET `/api/v1/runs/{run_id}/export`：导出报告文件（已实现）

### 具体用途

把已经人工批准的报告下载为 Markdown 或 PDF 文件。草稿即使可以通过 `/report` 查看，也不能通过本接口伪装成最终报告。

```http
GET {{baseUrl}}/api/v1/runs/31/export?format=markdown
```

| 参数 | 位置 | 可选值 | 默认值 |
|---|---|---|---|
| `run_id` | path | 已完成的任务 ID | 无 |
| `format` | query | `markdown`、`pdf` | `markdown` |

### 成功返回：200

Markdown 时：

```http
Content-Type: text/markdown
Content-Disposition: attachment; filename="legal-report-31-v2.md"
```

响应体是文件字节，不是下面这种 JSON。PDF 时 `Content-Type` 为 `application/pdf`。

### 常见错误

- 404：任务不存在。
- 409：报告尚未通过人工审批，或批准版本不存在。

## 5.2 POST `/api/v1/knowledge/articles`：新增单条法规

### 实际用途

向知识库写入一条经过人工核验的法规，并同步生成离线哈希检索向量。创建成功后无需重启服务，搜索接口可以立即检索到新条文。当前项目没有登录与权限系统，因此只能在本地或受信任网络中使用，不能直接暴露到公网。

### 请求

```json
{
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百八十条",
  "content": "当事人一方不履行非金钱债务或者履行非金钱债务不符合约定的……",
  "source": "国家法律法规数据库；访问日期：2026-07-23"
}
```

| 字段 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `law_name` | 是 | 2–200 字符 | 法律或法规名称 |
| `article_number` | 是 | 1–64 字符 | 条文编号，与法律名称共同用于判重 |
| `content` | 是 | 2–20000 字符 | 经人工核验的原文、节选或明确标注的教学要旨 |
| `source` | 是 | 2–500 字符 | 权威来源、链接、版本或访问日期 |

字段首尾空白会自动去除；只有空格的字段返回 422。

### 成功返回：201

```json
{
  "article_id": 11,
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百八十条",
  "content": "当事人一方不履行非金钱债务或者履行非金钱债务不符合约定的……",
  "source": "国家法律法规数据库"
}
```

创建时会同时写入 `legal_articles` 和 `article_embeddings`。可以立即调用 `POST /api/v1/articles/search` 验证，再用返回的 `article_id` 调用详情接口回查。

### 错误

- 409：相同法律名称和条文编号已经存在。
- 422：必填字段缺失或格式不正确。

## 5.3 POST `/api/v1/knowledge/articles/batch`：同步批量上传 TXT 法规

### 实际用途

一次上传 1–200 个小型 TXT。后端逐个解析、校验和判重，合法文件写入数据库并建立哈希检索索引；重复和错误文件不会阻断其他合法文件。

每个 UTF-8 TXT 的格式：

```text
中华人民共和国劳动合同法
第九条
https://www.samr.gov.cn/……
用人单位招用劳动者，不得扣押劳动者的居民身份证……
正文第二段（可选）
```

固定含义：

| 行 | 字段 | 说明 |
|---|---|---|
| 第 1 行 | `law_name` | 法律正式名称，2–200 字符 |
| 第 2 行 | `article_number` | 条号，1–64 字符 |
| 第 3 行 | `source` | 权威来源或版本说明，2–500 字符 |
| 第 4 行起 | `content` | 正文，可包含多段，合计 2–20000 字符 |

限制：最多 200 个文件；单个不超过 128 KB；整批不超过 8 MB；只接受 `.txt` 和 UTF-8（允许 BOM）。

### Apifox 请求

Body 选择 `form-data`，添加多个同名字段：

| Key | 类型 | 必填 | 值 |
|---|---|---|---|
| `files` | File | 是 | 第一个 TXT |
| `files` | File | 否 | 第二个 TXT，继续使用同一个 Key |

### 成功返回：200

```json
{
  "total": 3,
  "created_count": 1,
  "duplicate_count": 1,
  "invalid_count": 1,
  "items": [
    {
      "filename": "001.txt",
      "status": "created",
      "article_id": 37,
      "law_name": "中华人民共和国劳动合同法",
      "article_number": "第九条",
      "message": "法规已保存并建立检索索引"
    },
    {
      "filename": "002.txt",
      "status": "duplicate",
      "article_id": null,
      "law_name": "中华人民共和国劳动合同法",
      "article_number": "第九条",
      "message": "相同法律名称和条文编号已经存在"
    },
    {
      "filename": "broken.txt",
      "status": "invalid",
      "article_id": null,
      "law_name": null,
      "article_number": null,
      "message": "文件至少需要四行：名称、条号、来源、正文"
    }
  ]
}
```

HTTP 200 表示服务器已经完成整批处理，不表示每个文件都成功。调用方必须读取三个计数和 `items[].status`。`duplicate` 与 `invalid` 是文件级业务结果，不使用整个请求的 409 或 422。

### 整批错误

- 413：超过 200 个、单文件超过限制，或整批超过 8 MB；
- 422：没有提供 `files` 字段；
- 500：数据库或索引过程发生未预期异常。

项目提供 `examples/batch_laws/` 中 200 个示例，可直接在前端多选，也可在 Apifox 选择少量文件验证。

## 5.4 POST `/api/v1/knowledge/articles/normalize`：Agent 整理任意排版 TXT

### 具体含义

这个接口解决“用户拿到的 TXT 并不遵守四行协议”的问题。用户只需上传一份排版任意、理论上只包含一条法规的 UTF-8 TXT，在线 LLM 会从原文中提取：

1. 法律名称 `law_name`；
2. 条号 `article_number`；
3. 来源 `source`；
4. 条文正文 `content`。

然后服务端按“名称、条号、来源、正文”的顺序生成标准四行 TXT。模型被明确要求只能提取和清理排版，不能猜测缺失信息、概括正文或补写法律内容。

该接口是“转换草稿接口”，不是“知识库写入接口”：

- 不写 `legal_articles`；
- 不生成 Embedding；
- 不改变知识库数量；
- 返回值始终带 `requires_human_review=true`；
- 用户核对后可下载 TXT，或在前端填入“单条录入”表单再保存。

### Apifox 请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | 一个 UTF-8 `.txt`，不超过 128 KB，文本不超过 30000 字符 |

可以直接使用 `examples/unstructured_law_example.txt` 测试。

### 成功返回：200

```json
{
  "original_filename": "unstructured_law_example.txt",
  "standardized_filename": "unstructured_law_example_standardized.txt",
  "law_name": "中华人民共和国食品安全法",
  "article_number": "第四条",
  "source": "国家法律法规数据库",
  "content": "食品生产经营者对其生产经营食品的安全负责。",
  "confidence": 0.96,
  "missing_fields": [],
  "warnings": [],
  "multiple_articles_detected": false,
  "ready_for_import": true,
  "requires_human_review": true,
  "standardized_text": "中华人民共和国食品安全法\n第四条\n国家法律法规数据库\n食品生产经营者对其生产经营食品的安全负责。",
  "model": "deepseek-v4-flash"
}
```

### 字段如何判断

| 字段 | 含义 |
|---|---|
| `confidence` | 模型对字段提取的自评，不是法律真实性分数，也不能替代人工核验 |
| `missing_fields` | 未从原文中找到的字段名；标准文本中会出现 `[待补充……]` |
| `warnings` | 多条内容、字段无法在原文逐字定位等人工核对提示 |
| `multiple_articles_detected` | 模型认为文件含多个条号；当前只保留第一条草稿 |
| `ready_for_import` | 只有字段齐全且未发现多条内容时为 `true`，仍需人工核对 |
| `requires_human_review` | 当前固定为 `true`，提醒调用方不得把模型输出当作已核验法规 |
| `standardized_text` | 可以保存为 UTF-8 TXT 的标准四行内容，正文仍可包含后续多行 |
| `model` | 本次实际使用的 Chat 模型名 |

如果来源缺失，典型结果为：

```json
{
  "source": null,
  "missing_fields": ["source"],
  "ready_for_import": false,
  "standardized_text": "某法规\n第一条\n[待补充来源]\n原文正文"
}
```

### 错误

- 413：单个文件超过 128 KB；
- 415：不是 TXT 或 Content-Type 不受支持；
- 422：文件为空、不是 UTF-8、文本过长或内容无法解析；
- 502：模型服务失败，或者模型连续两次不能返回符合 Schema 的 JSON；
- 503：`OFFLINE_MODE=true`、没有配置 LLM Key，或在线 LLM 未启用。

### 为什么不自动入库

法律知识库要求可追溯和准确。LLM 即使返回合法 JSON，也可能把标题、条号或来源识别错。把“智能整理”和“正式入库”拆成两个动作，可以让模型负责非确定性提取，让数据库写入继续经过人工确认、字段校验和重复检查。

## 5.5 POST `/api/v1/knowledge/imports`：大型异步导入法规（规划）

### 计划用途

上传 JSONL、TXT 或 CSV 数据文件，创建后台导入任务。批量解析和向量化可能耗时，所以只返回 `job_id`，不在当前请求中等待完成。

### Apifox 计划请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 含义 |
|---|---|---|---|
| `file` | File | 是 | 待导入的法规文件 |
| `overwrite` | Text/Boolean | 否 | 重复数据是否覆盖，默认 `false` |

### 计划成功返回：202

```json
{
  "job_id": "77f58c78-c5c6-4f50-b7f3-8d5c802888fa",
  "status": "queued",
  "total": 0,
  "success": 0,
  "skipped": 0,
  "failed": 0,
  "errors": []
}
```

`202` 表示任务被接受，并不表示数据已经全部导入。

### 计划错误

- 415：文件格式不支持。
- 422：未上传文件或参数格式错误。

## 5.6 GET `/api/v1/knowledge/imports/{job_id}`：查询法规导入状态

### 计划用途

轮询批量导入任务，查看成功、跳过和失败数量，并获取逐条错误摘要。

```http
GET {{baseUrl}}/api/v1/knowledge/imports/77f58c78-c5c6-4f50-b7f3-8d5c802888fa
```

### 计划成功返回：200

```json
{
  "job_id": "77f58c78-c5c6-4f50-b7f3-8d5c802888fa",
  "status": "completed",
  "total": 100,
  "success": 96,
  "skipped": 3,
  "failed": 1,
  "errors": ["第 37 行缺少 article_number"]
}
```

状态可为 `queued`、`running`、`completed`、`failed`。`failed` 计数大于 0 不一定代表整个任务状态为 `failed`；部分成功的任务仍可完成。

## 5.7 POST `/api/v1/evaluations`：创建离线评测任务

### 计划用途

使用固定测试集对比不同检索方案，避免只凭几个手工问题判断效果。它用于回答“混合检索是否真的比关键词检索更好”。

### 计划请求

```json
{
  "dataset": "eval/dataset.jsonl",
  "strategies": ["keyword", "hash", "hybrid"],
  "top_k": 5
}
```

| 字段 | 必填 | 含义 |
|---|---|---|
| `dataset` | 是 | 项目内评测数据集路径或注册名称 |
| `strategies` | 是 | 需要对比的检索策略，至少一项 |
| `top_k` | 否 | 每个问题取前多少条法规，默认 5 |

### 计划成功返回：202

```json
{
  "evaluation_id": "f06cb7b3-e04b-4a61-85f8-fdc53044c163",
  "status": "queued",
  "progress": 0,
  "results": null,
  "error": null
}
```

## 5.8 GET `/api/v1/evaluations/{evaluation_id}`：查询评测状态与指标

### 计划用途

查看评测进度，并在完成后按策略返回分类、检索、引用、工作流成功率和性能指标。

```http
GET {{baseUrl}}/api/v1/evaluations/f06cb7b3-e04b-4a61-85f8-fdc53044c163
```

### 计划成功返回：200

```json
{
  "evaluation_id": "f06cb7b3-e04b-4a61-85f8-fdc53044c163",
  "status": "completed",
  "progress": 100,
  "results": {
    "keyword": {
      "case_type_accuracy": 0.84,
      "recall_at_5": 0.72,
      "mrr": 0.61,
      "citation_accuracy": 0.78,
      "workflow_success_rate": 0.98,
      "average_latency_ms": 45,
      "p95_latency_ms": 82
    },
    "hybrid": {
      "case_type_accuracy": 0.88,
      "recall_at_5": 0.86,
      "mrr": 0.74,
      "citation_accuracy": 0.85,
      "workflow_success_rate": 0.98,
      "average_latency_ms": 71,
      "p95_latency_ms": 130
    }
  },
  "error": null
}
```

指标解释：

| 指标 | 含义 |
|---|---|
| `case_type_accuracy` | 案件类型识别准确率 |
| `recall_at_5` | 正确法规是否出现在前 5 条中的比例 |
| `mrr` | 第一个正确结果排名的倒数均值，越高表示正确结果越靠前 |
| `citation_accuracy` | 最终引用中正确引用的比例 |
| `workflow_success_rate` | 完整工作流成功完成的比例 |
| `average_latency_ms` | 平均耗时 |
| `p95_latency_ms` | 95% 请求不超过的耗时 |

效果指标和延迟指标需要一起看。召回率提升但延迟大幅上升时，需要结合产品目标做取舍。

---

# 6. 统一错误理解

当前已实现接口主要使用 FastAPI 默认错误格式，未来会逐步统一为稳定的业务错误结构。

当前常见格式：

```json
{
  "detail": "未找到指定任务"
}
```

规划中的统一格式：

```json
{
  "code": "RUN_NOT_FOUND",
  "message": "未找到指定任务",
  "detail": null,
  "request_id": "req-20260722-0001"
}
```

| HTTP 状态 | 含义 | 调用方应该怎么做 |
|---|---|---|
| 400 | 请求语义错误 | 检查业务参数 |
| 404 | 路径、任务或资源不存在 | 检查 URL 和 ID；规划接口当前也会出现 |
| 409 | 当前资源状态不允许操作 | 先查询任务状态 |
| 415 | 文件类型不支持 | 改用 TXT、DOCX、PDF 或接口规定格式 |
| 422 | FastAPI 参数校验失败 | 查看 `detail[].loc` 和 `detail[].msg` |
| 429 | 请求过快或并发超限 | 等待后重试，生产环境使用退避策略 |
| 500 | 服务内部异常 | 保存请求信息并查服务日志 |
| 502 | 上游模型服务异常 | 检查模型地址、密钥和服务状态 |
| 504 | 上游模型请求超时 | 降级为离线模式或稍后重试 |

# 7. Apifox 完整自测顺序

1. 导入 `docs/openapi.json`，环境地址设为 `http://127.0.0.1:8000`。
2. 调用 `/health`，确认 `status=ok` 且 `article_count>0`。
3. 调用法规搜索，保存第一条的 `article_id`。
4. 用该 ID 调用法规详情，核对 `content`。
5. 调用 `/runs`，使用 `offline`，保存返回的 `run_id`。
6. 查询任务状态，确认 `status=completed`、`progress=100` 且 `traces` 包含四个核心节点。
7. 查询 citations，确认每条都有分数和审核状态。
8. 查询 report，确认有 Markdown、案件事实、证据缺口和引用。
9. 对一个 completed 任务调用 retry，预期得到 409，这是一条正确的负向测试。
10. 请求一个规划接口，当前预期为 404；不要把它记录为已实现功能缺陷。

# 8. 面试时如何解释这套接口设计

可以用下面这段逻辑回答：

> 我把简单同步接口和完整 Agent 任务接口分开。`/cases` 保留第一周的兼容能力，`/runs` 负责可观测的工作流执行。创建任务后，状态、引用和报告使用独立资源接口，既便于前端轮询，也便于审计和失败重试。引用同时保留关键词、语义和综合分数，并通过审核状态控制是否进入报告。接口在第二周先同步执行，但使用 202 和状态资源预留了异步迁移空间，因此第三周改后台任务时不需要破坏客户端契约。

如果被追问“为什么报告不直接放在创建任务响应里”，可以回答：任务执行时间和报告体积会增长；拆分后可以处理超时、失败重试、进度展示、权限控制和独立导出，也更符合资源化 API 设计。

# 9. 文档维护规则

- FastAPI 新增或修改路由时，同步更新 `docs/openapi.json` 和本文档。
- 接口完成后把 `x-implementation-status` 从 `planned` 改为 `implemented`。
- 返回字段发生变化时，同时更新成功示例、字段表和错误示例。
- Apifox 重新导入时使用智能合并，避免覆盖已有环境和测试用例。
- 示例中只能使用假数据，任何 API Key、数据库密码和用户材料都不能写进文档或版本库。

---

# 10. 第八周运行监控接口

## 10.1 `GET /api/v1/runs/{run_id}/monitoring`

### 作用

读取一次 Agent 运行的完整脱敏 Trace。它用来定位最慢节点、实际 provider/model、Token、估算费用、重试和降级原因，不返回案件全文、Prompt 或 API Key。

### 路径参数

| 参数 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `run_id` | integer | 是 | `POST /api/v1/runs` 返回的任务 ID |

### 返回示例

```json
{
  "run_id": 42,
  "trace_id": "fb8cd20bddf7466a8a85b9df19a3725f",
  "status": "waiting_for_approval",
  "mode": "agent",
  "model": "deepseek-v4-flash",
  "total_duration_ms": 8421,
  "input_tokens": 3560,
  "output_tokens": 1024,
  "estimated_cost_usd": 0.0032,
  "fallback_count": 0,
  "retry_count": 0,
  "slowest_node": "write_report",
  "slowest_node_duration_ms": 3610,
  "started_at": "2026-08-01T10:00:00Z",
  "completed_at": null,
  "spans": [
    {
      "span_id": "a8bd3c62e17019f4",
      "parent_span_id": "3457ec16583b43e1",
      "name": "gen_ai.chat",
      "node": "analyze_case",
      "status": "completed",
      "duration_ms": 1240,
      "provider": "openai-compatible",
      "model": "deepseek-v4-flash",
      "input_tokens": 720,
      "output_tokens": 210,
      "estimated_cost_usd": 0.00062,
      "retry_count": 0,
      "fallback_reason": null,
      "error_code": null,
      "attributes": {
        "run.id": 42,
        "agent.node": "analyze_case",
        "gen_ai.request.model": "deepseek-v4-flash"
      },
      "started_at": "2026-08-01T10:00:00.100000Z",
      "completed_at": "2026-08-01T10:00:01.340000Z"
    }
  ]
}
```

### 字段理解

| 字段 | 含义 |
|---|---|
| `trace_id` | 同一次 HTTP 创建请求和 Agent 工作流的关联 ID |
| `total_duration_ms` | 当前 Trace 中 `agent.invoke` 根 Span 的累计耗时 |
| `input_tokens` / `output_tokens` | Chat 与 Embedding 计量 Span 的累计 Token |
| `estimated_cost_usd` | 按运行时环境变量单价估算；默认单价为 0 |
| `fallback_count` | 出现 `fallback_reason` 的模型或 Embedding Span 数 |
| `retry_count` | LangGraph 补充检索重试次数 |
| `slowest_node` | 当前保存的 Agent 节点 Span 中耗时最长的节点 |
| `spans` | 按开始时间排列的脱敏链路，包含父子 Span ID |

### 常见错误

- 任务不存在：404，`{"detail":"未找到指定任务"}`；
- 历史任务没有 Trace：404，`{"detail":"该运行没有可观测性数据"}`。

## 10.2 `GET /api/v1/monitoring/overview`

### 作用

按最近若干天聚合 Agent 运行指标，供监控首页使用。

### 查询参数

| 参数 | 类型 | 默认 | 限制 | 含义 |
|---|---|---:|---:|---|
| `days` | integer | 7 | 1～90 | 从服务器当前时间向前统计的天数 |

### 返回示例

```json
{
  "days": 7,
  "run_count": 18,
  "success_rate": 0.9444,
  "fallback_rate": 0.1111,
  "average_duration_ms": 7250.5,
  "p95_duration_ms": 13200,
  "total_input_tokens": 48200,
  "total_output_tokens": 12600,
  "total_estimated_cost_usd": 0.0482,
  "node_metrics": [
    {
      "node": "analyze_case",
      "sample_count": 18,
      "average_duration_ms": 1210.4,
      "p95_duration_ms": 1980
    }
  ],
  "recent_runs": [
    {
      "run_id": 42,
      "trace_id": "fb8cd20bddf7466a8a85b9df19a3725f",
      "status": "waiting_for_approval",
      "mode": "agent",
      "model": "deepseek-v4-flash",
      "total_duration_ms": 8421,
      "input_tokens": 3560,
      "output_tokens": 1024,
      "estimated_cost_usd": 0.0032,
      "fallback_count": 0,
      "retry_count": 0,
      "created_at": "2026-08-01T10:00:00Z"
    }
  ]
}
```

`success_rate` 当前定义为“状态不是 `failed` 的运行比例”，因此等待追问、等待审批和已驳回的业务终态不被当成系统故障。`fallback_rate` 表示至少一个计量 Span 发生回退的运行比例。

## 10.3 第八周推荐调用顺序

```text
POST /api/v1/runs
  ↓ 保存 run_id、trace_id、monitoring_url
GET /api/v1/runs/{run_id}
  ↓ 读取进度、Token、费用与降级计数
GET /api/v1/runs/{run_id}/monitoring
  ↓ 定位这一次运行的最慢节点与失败原因
GET /api/v1/monitoring/overview?days=7
  ↓ 查看跨运行趋势
```

Apifox 导入 `docs/openapi.json` 后，这两个接口位于“运行监控”分组。
