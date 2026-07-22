from sqlalchemy import Engine, inspect, text


def ensure_runtime_schema(engine: Engine) -> None:
    """Apply the tiny SQLite-compatible migration needed by the portfolio app.

    A production service should use Alembic. This focused migration keeps an
    existing first/second-week database usable without deleting user runs.
    """

    inspector = inspect(engine)
    if "agent_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agent_runs")}
    if "started_at" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_runs ADD COLUMN started_at DATETIME"))
