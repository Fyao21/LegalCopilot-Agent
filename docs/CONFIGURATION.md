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

DeepSeek 的 Chat Completions 配置只用于案件分析、引用语义审核和报告写作。当前项目默认继续使用无需密钥的中文哈希 Embedding：

```env
EMBEDDING_PROVIDER=hash
```

如果以后接入具有 OpenAI 兼容 `/embeddings` 接口的服务，需要单独配置：

```env
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
EMBEDDING_MODEL=your-embedding-model
```

然后执行：

```powershell
python scripts\reindex_embeddings.py
```

不要因为 Chat 模型使用 DeepSeek，就默认把 DeepSeek 地址作为 Embedding 地址。两个服务在项目中是独立配置。

## 4. MySQL 配置

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

## 5. Redis 配置

Redis 在当前同步工作流中没有作用。第三周将任务改为后台执行时，可以用于：

- Celery/RQ 的消息代理；
- 任务状态缓存；
- 限流和幂等控制。

接入时使用独立变量，例如 `REDIS_URL=redis://:password@host:6379/0`，并避免把内网地址和真实密码写进示例配置。

## 6. RocketMQ 配置

当前 Python MVP 不需要 RocketMQ。第三周计划使用 FastAPI 后台任务，生产化时更适合先选择 Celery/RQ + Redis。只有在需要与已有 Java 微服务的 RocketMQ 事件体系集成时，再增加专门的消费者和生产者适配器。

## 7. Java 配置中不需要迁移的部分

以下配置属于原 Spring Boot 项目，不应复制到当前 Python 项目：

- `spring.application.name`；
- `spring.datasource.driver-class-name`；
- `spring.jackson`；
- `mybatis-plus`；
- Java RocketMQ producer group。

这些配置可以作为未来系统集成的背景资料，但不是 Legal Copilot Agent 当前运行所需配置。
