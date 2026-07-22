import logging
import time

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.database import SessionLocal
from app.models import AgentRun
from app.workflows import execute_agent_run

logger = logging.getLogger("legal_copilot.tasks")
MAX_DATABASE_LOCK_RETRIES = 2


def _is_database_lock(error: OperationalError) -> bool:
    return "database is locked" in str(error).lower()


def _mark_failed(run_id: int, error: Exception) -> None:
    try:
        with SessionLocal() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.current_node = "failed"
            run.error_code = type(error).__name__.upper()
            run.error_message = str(error)[:1000]
            db.commit()
    except SQLAlchemyError:
        logger.exception("background_run_failure_persist_failed", extra={"run_id": run_id})


def execute_agent_run_by_id(run_id: int) -> None:
    for attempt in range(MAX_DATABASE_LOCK_RETRIES + 1):
        try:
            with SessionLocal() as db:
                run = db.get(AgentRun, run_id)
                if run is None:
                    logger.warning("background_run_missing", extra={"run_id": run_id})
                    return
                execute_agent_run(db, run)
                return
        except OperationalError as error:
            if _is_database_lock(error) and attempt < MAX_DATABASE_LOCK_RETRIES:
                delay_seconds = 0.1 * (attempt + 1)
                logger.warning(
                    "background_run_database_locked",
                    extra={"run_id": run_id, "attempt": attempt + 1, "delay_seconds": delay_seconds},
                )
                time.sleep(delay_seconds)
                continue
            logger.exception("background_run_database_error", extra={"run_id": run_id})
            _mark_failed(run_id, error)
            return
        except Exception as error:
            logger.exception("background_run_unhandled_error", extra={"run_id": run_id})
            _mark_failed(run_id, error)
            return
