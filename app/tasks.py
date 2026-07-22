import logging

from app.database import SessionLocal
from app.models import AgentRun
from app.workflows import execute_agent_run


logger = logging.getLogger("legal_copilot.tasks")


def execute_agent_run_by_id(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        if run is None:
            logger.warning("background_run_missing", extra={"run_id": run_id})
            return
        execute_agent_run(db, run)
