# 律镜 Legal Copilot Agent：逐接口含义与返回示例

本文档面向两类读者：一类是希望使用 Apifox 调试项目的开发者，另一类是希望通过项目准备 Python、FastAPI、Agent 与后端岗位面试的学习者。

文档以当前项目代码和 `docs/openapi.json` 为准。每个接口都说明业务含义、请求方法、参数、返回字段、成功示例、常见错误和下一步调用。

## 1. 阅读前先区分接口状态

| 状态 | 含义 | 当前能否调用 |
|---|---|---|
| `implemented` | 已写入 FastAPI 路由并经过自动测试 | 可以 |
| `planned` | 已在 OpenAPI 中提前设计，供后续开发保持契约稳定 | 不可以，当前通常返回 `404 Not Found` |

当前共定义 15 个接口：10 个已实现，5 个处于规划阶段。规划接口中的响应 JSON 是“预期契约示例”，不是当前服务真实返回。

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
| `application/json` | 法规搜索、知识库单条新增、评测 | Body → JSON |
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
GET /api/v1/runs/{run_id}/citations
  → 检查引用及审核状态
GET /api/v1/runs/{run_id}/report
  → 读取最终报告
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
  "article_count": 10
}
```

字段含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `status` | string | `ok` 表示服务和本次检查正常 |
| `article_count` | integer | 数据库中当前法规条文数量；首次启动通常为 10 |

`article_count` 大于 0 说明样例法规已经初始化。它不是业务结果总数，也不是 Agent 任务数。

### 常见问题

- 浏览器访问 `/` 返回 `{"detail":"Not Found"}` 是正常的，因为项目没有定义首页。
- 应访问 `/health` 或 `/docs`。
- 无法连接通常表示服务未启动、端口被占用或运行配置的工作目录不正确。

### 下一步

调用法规搜索接口，验证数据库内容是否真正可检索。

## 4.2 POST `/api/v1/articles/search`：搜索相关法规

### 具体含义

把自然语言法律问题转换为检索请求，在本地法规知识库中返回相关度最高的 Top-K 条文。当前实现结合关键词和语义分数；离线模式使用本地哈希向量，不需要大模型密钥。

### 请求

Content-Type：`application/json`

```json
{
  "query": "合同没有履行，可以要求赔偿损失吗",
  "limit": 5
}
```

| 字段 | 必填 | 约束 | 含义 |
|---|---|---|---|
| `query` | 是 | 至少 2 个字符 | 用户问题或检索关键词 |
| `limit` | 否 | 1～20，默认 5 | 最多返回多少条法规 |

### 成功返回：200

```json
[
  {
    "article_id": 3,
    "law_name": "中华人民共和国民法典",
    "article_number": "第五百七十七条",
    "excerpt": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
    "source": "项目内置教学样例",
    "score": 0.6432,
    "keyword_score": 0.5714,
    "semantic_score": 0.6819
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

分数只用于当前候选集内比较，不能解释为“法律结论有 64.32% 正确”。

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

## 4.3 GET `/api/v1/articles/{article_id}`：获取法规条文详情

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
  "source": "项目内置教学样例"
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

## 4.4 POST `/api/v1/cases`：同步分析案件（兼容接口）

### 具体含义

这是第一周保留的同步接口。它接收用户问题和可选案件文件，在一次 HTTP 请求中完成文本解析、案件要素提取和法规检索，并返回简化结果。

新功能建议优先调用 `/api/v1/runs`，因为后者能查看节点轨迹、引用审核和完整报告。

### Apifox 请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 示例 |
|---|---|---|---|
| `question` | Text | 是 | `供应商收款后未按合同交货，我能否解除合同并要求赔偿？` |
| `file` | File | 否 | `contract.txt`、`contract.docx` 或 `contract.pdf` |

只填写问题也可以调用。

### 成功返回：201

```json
{
  "run_id": 21,
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
      "article_id": 3,
      "law_name": "中华人民共和国民法典",
      "article_number": "第五百七十七条",
      "excerpt": "当事人一方不履行合同义务……应当承担违约责任。",
      "source": "项目内置教学样例",
      "score": 0.6432,
      "keyword_score": 0.5714,
      "semantic_score": 0.6819
    }
  ],
  "notice": "本结果仅用于技术演示，不构成法律意见。"
}
```

`facts` 各字段：

| 字段 | 含义 |
|---|---|
| `case_type` | 识别出的案件类别，如合同纠纷、劳动争议 |
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

## 4.5 POST `/api/v1/runs`：创建 Agent 分析任务

### 具体含义

这是项目的核心入口。请求会执行完整 LangGraph 工作流：案件要素分析 → 法规检索 → 引用审核 → 报告生成，并持久化运行状态和节点轨迹。

### Apifox 请求

Body 选择 `form-data`：

| Key | 类型 | 必填 | 默认值 | 含义 |
|---|---|---|---|---|
| `question` | Text | 是 | 无 | 用户的法律问题，2～5000 字符 |
| `mode` | Text | 否 | `offline` | `offline` 或 `agent` |
| `file` | File | 否 | 无 | TXT、DOCX 或 PDF 案件材料 |

示例：

```text
question = 供应商收款后未按合同交货，我能否解除合同并要求赔偿？
mode = offline
```

模式区别：

- `offline`：规则分析、本地哈希向量和模板报告，不需要网络或 API Key。
- `agent`：当 `OFFLINE_MODE=false` 且 LLM 配置完整时请求模型；不可用时进行安全降级。

### 成功返回：202

```json
{
  "run_id": 31,
  "status": "queued",
  "status_url": "/api/v1/runs/31",
  "report_url": "/api/v1/runs/31/report"
}
```

| 字段 | 含义 |
|---|---|
| `run_id` | 本次任务 ID，后续三个查询接口都使用它 |
| `status` | 创建响应固定为 `queued`，后续通过状态接口观察变化 |
| `status_url` | 状态查询相对地址 |
| `report_url` | 报告查询相对地址 |

为什么使用 202：服务器已经接受任务，但分析仍在后台执行。调用方不应等待创建请求直接返回报告，而应保存 `run_id` 并轮询状态接口。

### 常见错误

- 415：文件扩展名不受支持。
- 422：问题太短、过长，或 `mode` 不是 `offline/agent`。
- 429：规划中的并发或频率限制；当前不一定触发。

### 下一步

保存 `run_id`，先调用任务状态接口，不要直接假定报告已经可以读取。

## 4.6 GET `/api/v1/runs/{run_id}`：查询任务状态和节点轨迹

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
  "current_node": "write_report",
  "progress": 100,
  "retry_count": 0,
  "mode": "offline",
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

常见状态：`queued`、`parsing`、`analyzing`、`retrieving`、`reviewing`、`writing`、`completed`、`failed`。

执行来源字段：

- `execution_engine=pending`：任务尚未完成，暂时不能判断最终引擎；
- `execution_engine=rules`：离线规则和模板完成，未调用模型；
- `execution_engine=llm`：至少成功使用了 `model` 指定的模型；
- `execution_engine=fallback`：用户选择 Agent，但模型不可用或配置关闭，最终由离线方案完成；
- `model`：实际记录的模型名；离线完成通常为 `offline-template`。

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

## 4.7 POST `/api/v1/runs/{run_id}/retry`：重试失败任务

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

## 4.8 GET `/api/v1/runs/{run_id}/citations`：获取任务引用及审核结果

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

实际产品中，只有 `verified=true` 的引用才应进入最终法律分析正文。仍应通过 `article_id` 回查原文和权威来源。

### 不存在：404

```json
{
  "detail": "未找到指定任务"
}
```

## 4.9 GET `/api/v1/runs/{run_id}/report`：获取结构化分析报告

### 具体含义

任务完成后返回最终 Markdown 报告、结构化案件事实、证据缺口、通过审核的引用和生成元数据。前端既可以直接渲染 `markdown`，也可以使用结构化字段制作自己的页面。

### 请求

```http
GET {{baseUrl}}/api/v1/runs/31/report
```

### 成功返回：200

```json
{
  "run_id": 31,
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
      "article_id": 3,
      "law_name": "中华人民共和国民法典",
      "article_number": "第五百七十七条",
      "excerpt": "当事人一方不履行合同义务……",
      "source": "项目内置教学样例",
      "score": 0.6432,
      "keyword_score": 0.5714,
      "semantic_score": 0.6819,
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

把已完成报告下载为 Markdown 或 PDF 文件，而不是返回 JSON。

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
Content-Disposition: attachment; filename="legal-report-31.md"
```

响应体是文件字节，不是下面这种 JSON。PDF 时 `Content-Type` 为 `application/pdf`。

### 常见错误

- 404：任务不存在。
- 409：任务未完成或报告不存在。

## 5.2 POST `/api/v1/knowledge/articles`：新增单条法规

### 计划用途

由管理员写入一条经过人工核验的法规，并为它生成检索向量。这个接口不应开放给普通匿名用户。

### 计划请求

```json
{
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百八十条",
  "content": "当事人一方不履行非金钱债务或者履行非金钱债务不符合约定的……",
  "source": "国家法律法规数据库",
  "effective_date": "2021-01-01"
}
```

### 计划成功返回：201

```json
{
  "article_id": 11,
  "law_name": "中华人民共和国民法典",
  "article_number": "第五百八十条",
  "content": "当事人一方不履行非金钱债务或者履行非金钱债务不符合约定的……",
  "source": "国家法律法规数据库"
}
```

### 计划错误

- 409：相同法律名称和条文编号已经存在。
- 422：必填字段缺失或格式不正确。

## 5.3 POST `/api/v1/knowledge/imports`：批量导入法规

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

## 5.4 GET `/api/v1/knowledge/imports/{job_id}`：查询法规导入状态

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

## 5.5 POST `/api/v1/evaluations`：创建离线评测任务

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

## 5.6 GET `/api/v1/evaluations/{evaluation_id}`：查询评测状态与指标

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
