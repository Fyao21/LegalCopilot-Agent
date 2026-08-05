from sqlalchemy import Engine, inspect, text


def _add_missing_columns(
    engine: Engine,
    table_name: str,
    additions: dict[str, str],
) -> None:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing = {name: definition for name, definition in additions.items() if name not in columns}
    if not missing:
        return
    with engine.begin() as connection:
        for name, definition in missing.items():
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def ensure_runtime_schema(engine: Engine) -> None:
    """Apply the tiny SQLite-compatible migration needed by the portfolio app.

    A production service should use Alembic. This focused migration keeps an
    existing first/second-week database usable without deleting user runs.
    """

    _add_missing_columns(
        engine,
        "agent_runs",
        {
            "started_at": "DATETIME",
            "clarification_round": "INTEGER NOT NULL DEFAULT 0",
            "state_version": "INTEGER NOT NULL DEFAULT 0",
            "current_report_version": "INTEGER NOT NULL DEFAULT 0",
            "approved_report_version": "INTEGER",
            "checkpoint_thread_id": "VARCHAR(100)",
            "as_of_date": "DATE",
            "trace_id": "VARCHAR(32)",
            "total_duration_ms": "INTEGER NOT NULL DEFAULT 0",
            "input_tokens": "INTEGER NOT NULL DEFAULT 0",
            "output_tokens": "INTEGER NOT NULL DEFAULT 0",
            "estimated_cost_cny": "FLOAT NOT NULL DEFAULT 0",
            "fallback_count": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    _add_missing_columns(
        engine,
        "agent_run_spans",
        {"estimated_cost_cny": "FLOAT NOT NULL DEFAULT 0"},
    )
    _add_missing_columns(engine, "case_runs", {"as_of_date": "DATE"})
    _add_missing_columns(engine, "legal_articles", {"law_version_id": "INTEGER"})
    _add_missing_columns(engine, "retrieval_logs", {"law_version_id": "INTEGER"})
    _add_missing_columns(engine, "agent_run_citations", {"law_version_id": "INTEGER"})

    inspector = inspect(engine)
    if "agent_runs" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("agent_runs")}
    if "uq_agent_runs_checkpoint_thread_id" not in indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_checkpoint_thread_id "
                    "ON agent_runs (checkpoint_thread_id)"
                )
            )
    if "uq_agent_runs_trace_id" not in indexes:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_trace_id ON agent_runs (trace_id)")
            )
    index_statements = (
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_as_of_date ON agent_runs (as_of_date)",
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_trace_id ON agent_runs (trace_id)",
        "CREATE INDEX IF NOT EXISTS ix_case_runs_as_of_date ON case_runs (as_of_date)",
        "CREATE INDEX IF NOT EXISTS ix_legal_articles_law_version_id ON legal_articles (law_version_id)",
        "CREATE INDEX IF NOT EXISTS ix_retrieval_logs_law_version_id ON retrieval_logs (law_version_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_run_citations_law_version_id "
        "ON agent_run_citations (law_version_id)",
    )
    with engine.begin() as connection:
        for statement in index_statements:
            connection.execute(text(statement))
