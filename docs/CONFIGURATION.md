# 配置迁移说明

## 1. 安全处理

不要把真实 API Key、数据库密码或 Redis 密码提交到项目中。真实配置只放在项目根目录的 `.env`，该文件已经被 `.gitignore` 排除。

如果密钥或密码曾经粘贴到聊天、Issue、提交记录或截图中，应当在对应服务端立即撤销并重新生成，不能只在本地修改字符串。

## 2. DeepSeek 配置

项目同时支持自己的变量名和常见 OpenAI 兼容变量名。

推荐写法：

```env
OFFLINE_MODE=false
LLM_API_KEY=your_new_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

兼容旧项目的写法：

```env
OFFLINE_MODE=false
OPENAI_API_KEY=your_new_key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

读取优先级：

1. `LLM_API_KEY` 优先于 `OPENAI_API_KEY`；
2. `LLM_BASE_URL` 优先于 `OPENAI_BASE_URL`；
3. `LLM_MODEL` 优先于 `MODEL_NAME`。

修改 `.env` 后必须重新启动 PyCharm 里的服务，因为配置在 Python 进程内有缓存。

## 3. Embedding 配置

DeepSeek 的 Chat Completions 配置只用于案件分析、引用语义审核和报告写作。DeepSeek 官方当前公开文档列出的是 Chat/Completions 模型，没有可供本项目调用的 `/embeddings` 模型，因此不能复用 `LLM_BASE_URL=https://api.deepseek.com` 作为 Embedding 地址。

项目默认继续使用无需密钥的中文哈希 Embedding：

```env
OFFLINE_MODE=true
EMBEDDING_PROVIDER=hash
```

Provider 选择规则：

| 配置 | 实际行为 |
|---|---|
| `OFFLINE_MODE=true` | 强制使用 `hash`，不访问网络 |
| `OFFLINE_MODE=false` 且 `EMBEDDING_PROVIDER=hash` | Chat 可在线，但检索继续使用哈希 |
| `OFFLINE_MODE=false` 且 `EMBEDDING_PROVIDER=openai-compatible` | 调用独立的 `/embeddings` 服务 |
| 在线服务认证失败、超时或返回异常 | 当前检索回滚并降级到 `hash` |

### 3.1 接入阿里云百炼 text-embedding-v4

先在百炼控制台创建 API Key 和工作空间，然后在 `.env` 中配置：

```env
OFFLINE_MODE=false
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_API_KEY=你的百炼API-Key
EMBEDDING_BASE_URL=https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BATCH_SIZE=10
```

不同地域的 Key、Workspace ID 和 Base URL 不通用，必须使用百炼控制台展示的实际地址。官方说明见：`https://help.aliyun.com/zh/model-studio/embedding`。

`text-embedding-v4` 默认返回 1024 维稠密向量。项目会读取服务实际返回的维度，不需要把 `EMBEDDING_DIMENSIONS` 改为 1024；`EMBEDDING_DIMENSIONS` 只控制本地哈希向量。批量大小默认 10，避免一次发送 36 条法规超过服务限制。

### 3.2 建立在线索引

保存 `.env` 并停止后端。先用一条短文本验证配置，脚本不会打印 Key：

```powershell
python scripts\check_embedding.py
```

在线成功示例：

```text
embedding_check=ok mode=online provider=openai-compatible model=text-embedding-v4 dimensions=1024 nonzero=1024
```

确认成功后再为全部法规建立索引：

```powershell
python scripts\reindex_embeddings.py
```

成功示例：

```text
provider=openai-compatible model=text-embedding-v4 updated=36
```

`article_embeddings` 会同时保留两组记录：

```text
hash / chinese-bigram-sha256-v1
openai-compatible / text-embedding-v4
```

不同 provider/model 使用联合唯一键，不会用在线向量覆盖离线向量。首次建立 36 条法规的在线索引会产生 API 调用和费用；正文、provider 和 model 都不变时再次执行，`updated=0`。

### 3.3 验证实际使用的模型

重新启动后端，调用：

```powershell
curl.exe -i -X POST "http://127.0.0.1:8000/api/v1/articles/search" `
  -H "Content-Type: application/json" `
  -d '{"query":"公司没有签劳动合同并拖欠工资","limit":5}'
```

在线成功时响应头应包含：

```text
X-Embedding-Provider: openai-compatible
X-Embedding-Model: text-embedding-v4
```

如果显示 `hash`，依次检查：

1. 是否已经重启后端；
2. `OFFLINE_MODE` 是否仍为 `true`；
3. provider 是否准确写成 `openai-compatible`；
4. Embedding Key、地域、Workspace ID、Base URL 和模型名是否匹配；
5. 后端日志是否出现 `embedding_provider_configuration_fallback` 或 `embedding_provider_request_fallback`。

Agent 任务的 `retrieve_laws` 节点轨迹也会记录 `provider`。离线模式始终强制使用哈希；Agent 模式才按照在线配置选择 provider。

在线模式发生网络超时或供应商瞬时错误时，服务会在同一个检索节点重试一次。只有连续两次失败才回退 hash，此时轨迹会同时显示：

```text
provider=hash，回退原因=openai-compatible/模型名 连续 2 次请求失败：……
```

首次为大量新法规补建真实向量时耗时会明显高于普通查询。补建完成后，同一 provider/model 的后续查询只需要生成查询向量，不会重复为所有法规建索引。

## 4. 多轮追问配置

第五周的多轮追问同时支持离线和 Agent 模式：

```env
MAX_CLARIFICATION_ROUNDS=3
MAX_QUESTIONS_PER_ROUND=5
```

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `MAX_CLARIFICATION_ROUNDS` | 3 | 同一个任务允许暂停追问的最大轮数，至少为 1 |
| `MAX_QUESTIONS_PER_ROUND` | 5 | 每轮最多向用户展示的问题数，代码强制限制在 1～5 |

达到轮数上限后不会无限等待，而是保留 `missing_information` 并继续检索与生成报告。用户可以明确回答“暂不清楚”，系统不会要求用户猜测。

SQLite 模式下，LangGraph checkpoint 与业务表共用 `data/legal_copilot.db`。除原有业务表外会出现：

- `agent_clarifications`：问题、回答、状态版本和幂等键；
- `report_versions`：每版报告 Markdown、事实/引用快照、修改摘要和发布状态；
- `agent_approvals`：批准、要求修改或驳回决定，包含审核人、意见、状态版本和幂等键；
- `checkpoints`、`checkpoint_blobs`、`checkpoint_writes`、`checkpoint_migrations`：由 `langgraph-checkpoint-sqlite` 管理的工作流状态。

这些 checkpoint 表不是法规向量，也不应手工编辑。数据库文件已经被 Git 忽略。

## 4.1 报告审批不需要新增环境变量

第六周审批功能默认使用现有 SQLite 和 LangGraph checkpointer，不要求 Redis、MySQL 或额外 API Key。离线模式也可以完整演示批准、修改、驳回、版本差异和最终导出。

- `reviewer` 目前是审批请求中的展示/审计字段，不是已经登录的真实账号；
- 身份认证与 RBAC 属于第十周，当前本地演示环境不能据此提供生产权限隔离；
- Agent 模式下“要求修改”可以使用已配置 Chat LLM 语义修订；
- 离线模式为避免编造事实，只在新版本中追加审批修改说明，并要求继续人工核对；
- 新生成报告必须为 `approved` 才能通过导出接口下载；
- 0.9.0 之前已经处于 `completed` 且没有版本记录的历史报告保留兼容下载。

## 4.2 法规时效检索不需要新增环境变量

第七周法规版本功能使用请求中的 `as_of_date` 和 SQLite 表数据，不需要额外 Key、Redis 或定时任务配置。

- `POST /api/v1/articles/search` 在 JSON 中传 `as_of_date: "2020-12-31"`；
- `POST /api/v1/cases` 与 `POST /api/v1/runs` 在 form-data 中传同名字段；
- 留空时检索服务使用服务器当前日期，但运行记录保留 `null`，表示用户没有显式选择日期；
- 日期有效区间固定为 `[effective_from, effective_to)`，不要通过环境变量改变边界语义；
- 应用启动时会创建 `laws`、`law_versions`，并为已有条文增量回填 `law_version_id`；
- 已废止版本仍可用于其历史有效期，但不会出现在当前日期结果中。

当前版本没有法规官方同步任务、来源过期阈值或地区配置。生产环境应通过受审计的导入流程更新版本，不要直接修改数据库日期来迎合检索结果。

## 4.3 Agent 运行监控与费用配置

第八周默认开启本地 OpenTelemetry 埋点：

```env
OBSERVABILITY_ENABLED=true
TELEMETRY_SERVICE_NAME=legal-copilot-agent
LLM_INPUT_COST_PER_1M_CNY=0
LLM_OUTPUT_COST_PER_1M_CNY=0
EMBEDDING_COST_PER_1M_CNY=0
```

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `OBSERVABILITY_ENABLED` | `true` | 是否创建 OpenTelemetry Span 和本地监控记录 |
| `TELEMETRY_SERVICE_NAME` | `legal-copilot-agent` | OpenTelemetry Resource 的服务名 |
| `LLM_INPUT_COST_PER_1M_CNY` | `0` | Chat 输入每百万 Token 人民币单价 |
| `LLM_OUTPUT_COST_PER_1M_CNY` | `0` | Chat 输出每百万 Token 人民币单价 |
| `EMBEDDING_COST_PER_1M_CNY` | `0` | Embedding 输入每百万 Token 人民币单价 |

注意：

1. 单价必须查询你实际使用的服务商和模型，文档不提供会过期的价格；
2. 默认 0 表示继续统计 Token，但费用显示 `¥0.000000`；
3. 单价只影响新 Span，修改配置不会重算历史运行；
4. 服务商返回 `usage` 时使用真实计数；没有 usage 时使用代码中的明确近似值；
5. 监控数据写入 `agent_runs` 和 `agent_run_spans`，不需要 Redis、MySQL 或独立监控服务器；
6. 当前未配置 OTLP Exporter，所以不会自动把数据发送到云端；
7. 关闭 `OBSERVABILITY_ENABLED` 适合特殊本地调试，但会导致新任务没有完整监控数据，不建议用于演示。

本机使用 `deepseek-v4-flash` 与 `text-embedding-v4` 时，可根据服务商实际报价配置。按用户提供的 2026-08-01 报价、对输入采用保守的“缓存未命中”单价：

```env
LLM_INPUT_COST_PER_1M_CNY=1
LLM_OUTPUT_COST_PER_1M_CNY=2
EMBEDDING_COST_PER_1M_CNY=0.5
```

缓存命中输入单价与未命中不同。当前版本没有单独统计缓存命中 Token，因此使用未命中价格作为偏保守估算。

允许进入 Span 的属性采用固定白名单，只包含任务/线程 ID、模式、节点、状态、provider/model、Token、候选数、审核数、重试与降级原因。案件全文、上传材料、Prompt、API Key、认证头和密码都不会作为 Span 属性保存。

## 5. MySQL 配置

当前项目使用项目内 SQLite：

```text
data/legal_copilot.db
```

因此 `MYSQL_HOST`、`MYSQL_PORT`、Spring `datasource` 和 MyBatis-Plus 配置当前不会被读取。这样设计是为了让求职项目无需先安装 MySQL 就能运行。

第三或第四周如果决定迁移 MySQL，需要单独完成以下工作：

1. 安装 Python MySQL 驱动，例如 PyMySQL；
2. 将配置转换为 SQLAlchemy `DATABASE_URL`；
3. 使用 Alembic 管理表结构迁移；
4. 验证 JSON 字段、索引、外键和事务行为；
5. 保留 SQLite 作为自动测试数据库。

不要把 Spring Boot 的 JDBC URL 或 YAML 直接复制到 Python `.env`，SQLAlchemy 不能直接使用 `jdbc:mysql://...` 格式。

## 6. Redis 配置

Redis 在当前同步工作流中没有作用。第三周将任务改为后台执行时，可以用于：

- Celery/RQ 的消息代理；
- 任务状态缓存；
- 限流和幂等控制。

接入时使用独立变量，例如 `REDIS_URL=redis://:password@host:6379/0`，并避免把内网地址和真实密码写进示例配置。

## 7. RocketMQ 配置

当前 Python MVP 不需要 RocketMQ。第三周计划使用 FastAPI 后台任务，生产化时更适合先选择 Celery/RQ + Redis。只有在需要与已有 Java 微服务的 RocketMQ 事件体系集成时，再增加专门的消费者和生产者适配器。

## 8. Java 配置中不需要迁移的部分

以下配置属于原 Spring Boot 项目，不应复制到当前 Python 项目：

- `spring.application.name`；
- `spring.datasource.driver-class-name`；
- `spring.jackson`；
- `mybatis-plus`；
- Java RocketMQ producer group。

这些配置可以作为未来系统集成的背景资料，但不是 Legal Copilot Agent 当前运行所需配置。
