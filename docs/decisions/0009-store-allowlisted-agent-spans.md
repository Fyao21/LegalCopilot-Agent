# ADR 0009：本地持久化经过白名单过滤的 Agent Span

- 状态：已接受
- 日期：2026-08-01
- 版本：1.2.0

## 背景

原有 `node_traces` 只有节点、耗时和动作摘要，无法稳定关联 HTTP 请求、LangGraph 节点、Chat、Embedding、Token、费用、重试与降级。直接把完整 Prompt、案件材料或工具参数发送到监控系统又会扩大敏感数据暴露面。

项目还需要保持零外部依赖启动，不能为了第八周监控强制安装 Collector、Prometheus、Redis 或云端 APM。

## 决策

1. 使用 OpenTelemetry API/SDK 创建 Trace 与 Span；
2. 创建任务时复用 FastAPI 请求 Trace ID，Agent 根 Span 延续同一 Trace；
3. 使用 `agent_run_spans` 在 SQLite 保存查询页面所需的 Span 快照；
4. `agent_runs` 只保存总耗时、Token、费用和降级数等聚合值；
5. Span 属性必须通过固定 allowlist，只允许任务/线程 ID、模式、节点、provider/model、Token、候选数、审核数、重试和降级原因；
6. 案件全文、材料、Prompt、API Key、认证头、密码和身份信息不得进入 Span 属性；
7. 费用按环境变量中的每百万 Token 单价估算，默认单价为 0；
8. 不配置 OTLP Exporter，生产导出与告警留作独立部署能力。

## 后果

正面影响：

- 本地即可按 Trace ID 定位最慢节点、模型、Token、费用与降级；
- 监控页不依赖第九周持久队列；
- 同一 SQLite 事务可以保证 Span 与任务数据可回查；
- allowlist 把可观测性数据泄漏风险限制在明确边界内；
- 后续接入 OTLP 时不需要改变业务接口。

代价与限制：

- SQLite 不适合高吞吐遥测和长期保留；
- 本地聚合没有 Prometheus 的时间序列查询与告警能力；
- 跨进程父 Span 的精确远程上下文传播仍可继续完善；
- 费用是工程估算，不是服务商账单；
- 禁止全文会降低某些问题的直接调试便利，需要通过 run ID 回到受控业务数据排查。

## 被否决方案

1. **只保留原 `node_traces`**：无法表示模型子调用、Token、父子关系和回退。
2. **记录完整 Prompt 与输出**：调试方便，但不符合案件隐私和最小化原则。
3. **第八周直接强制部署云 APM**：破坏项目零依赖本地演示，也会让本周功能依赖外部账号。
4. **只在内存统计**：应用重启后无法回查历史运行，前端也无法稳定展示。
