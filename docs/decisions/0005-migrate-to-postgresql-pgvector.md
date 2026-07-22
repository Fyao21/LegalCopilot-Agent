# ADR-0005：迁移 PostgreSQL 与 pgvector 的条件

- 状态：条件性决策
- 日期：2026-07-23

## 当前方案

SQLite 保存业务数据和 JSON 向量，检索时在 Python 中计算相似度。它适合 10 条教学法规和单机演示。

## 迁移触发条件

满足任一条件时评估 PostgreSQL：

- 法规或切片达到十万级，Python 全量扫描延迟不可接受；
- 需要多实例部署、并发写入、事务隔离和备份恢复；
- 需要租户隔离、行级权限和审计；
- 需要 pgvector 的 HNSW/IVFFlat 索引和元数据过滤。

## 迁移步骤

先用 Alembic 管理 Schema，再迁移业务表；向量列改为 `vector(n)`；建立 HNSW 索引；使用影子流量对比 Recall 与延迟；最后切换连接字符串。SQLite 仍保留为本地演示配置。
