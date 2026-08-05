import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import AgentClarification
from app.schemas import CaseFacts
from app.services.case_agent import CaseAnalysisOutcome
from app.services.embedding_provider import HashEmbeddingProvider


class FifthWeekClarificationTests(unittest.TestCase):
    question = "供应商收款后一直没有交货，我能解除合同并要求赔偿吗？"

    def setUp(self) -> None:
        self.embedding_patcher = patch(
            "app.services.retrieval_service.get_embedding_provider",
            return_value=HashEmbeddingProvider(),
        )
        self.embedding_patcher.start()

    def tearDown(self) -> None:
        self.embedding_patcher.stop()

    def _create_waiting_run(self, client: TestClient) -> tuple[int, dict]:
        created = client.post(
            "/api/v1/runs",
            data={"question": self.question, "mode": "offline"},
        )
        self.assertEqual(created.status_code, 202)
        run_id = created.json()["run_id"]
        status = client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "waiting_for_user")
        self.assertEqual(status.json()["progress"], 35)
        self.assertEqual(status.json()["state_version"], 1)
        self.assertEqual(status.json()["clarification_round"], 1)
        pending = client.get(f"/api/v1/runs/{run_id}/pending-action")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["action"]["type"], "clarification")
        return run_id, pending.json()

    def _answer(
        self,
        client: TestClient,
        run_id: int,
        pending: dict,
        *,
        state_version: int | None = None,
        idempotency_key: str | None = None,
        answer: str = "合同约定交货日期为2026年6月30日。",
    ):
        question_id = pending["action"]["questions"][0]["question_id"]
        return client.post(
            f"/api/v1/runs/{run_id}/clarifications",
            headers={"Idempotency-Key": idempotency_key or f"answer-{run_id}-round-1"},
            json={
                "expected_state_version": (
                    pending["state_version"] if state_version is None else state_version
                ),
                "answers": [{"question_id": question_id, "answer": answer}],
            },
        )

    def _approve(self, client: TestClient, run_id: int):
        pending = client.get(f"/api/v1/runs/{run_id}/pending-action").json()
        self.assertEqual(pending["action"]["type"], "approval")
        return client.post(
            f"/api/v1/runs/{run_id}/approvals",
            headers={"Idempotency-Key": f"fifth-week-approve-{run_id}-{pending['action']['action_id']}"},
            json={
                "expected_state_version": pending["state_version"],
                "action": "approve",
                "comment": "第五周回归测试审批",
                "reviewer": "自动测试",
            },
        )

    def test_pause_answer_resume_and_generate_current_final_report(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_waiting_run(client)
            submitted = self._answer(client, run_id, pending)

            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(submitted.json()["status"], "resuming")
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "waiting_for_approval")
            draft_export = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            self.assertEqual(draft_export.status_code, 409)
            approved = self._approve(client, run_id)
            self.assertEqual(approved.status_code, 202)
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["state_version"], 5)
            self.assertEqual(status["clarification_round"], 1)
            nodes = [item["node"] for item in status["traces"]]
            self.assertIn("clarify_user", nodes)
            report = client.get(f"/api/v1/runs/{run_id}/report")
            markdown = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            pdf = client.get(f"/api/v1/runs/{run_id}/export?format=pdf")
            self.assertEqual(report.status_code, 200)
            self.assertEqual(markdown.status_code, 200)
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_waiting_checkpoint_can_resume_after_test_client_restart(self) -> None:
        with TestClient(app) as first_client:
            run_id, pending = self._create_waiting_run(first_client)

        with TestClient(app) as restarted_client:
            restored = restarted_client.get(f"/api/v1/runs/{run_id}/pending-action")
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["action"]["action_id"], pending["action"]["action_id"])
            submitted = self._answer(restarted_client, run_id, restored.json())
            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(
                restarted_client.get(f"/api/v1/runs/{run_id}").json()["status"],
                "waiting_for_approval",
            )
            self.assertEqual(self._approve(restarted_client, run_id).status_code, 202)
            self.assertEqual(
                restarted_client.get(f"/api/v1/runs/{run_id}").json()["status"],
                "completed",
            )

    def test_stale_state_version_is_rejected(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_waiting_run(client)
            response = self._answer(client, run_id, pending, state_version=0)
            self.assertEqual(response.status_code, 409)
            self.assertIn("当前版本", response.json()["detail"])

    def test_all_pending_questions_must_be_answered(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_waiting_run(client)
            response = client.post(
                f"/api/v1/runs/{run_id}/clarifications",
                headers={"Idempotency-Key": f"missing-{run_id}-answer"},
                json={
                    "expected_state_version": pending["state_version"],
                    "answers": [{"question_id": "unknown-question", "answer": "测试"}],
                },
            )
            self.assertEqual(response.status_code, 422)
            self.assertIn("缺少回答", response.json()["detail"])
            self.assertIn("未知问题", response.json()["detail"])

    def test_duplicate_idempotency_key_does_not_resume_twice(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_waiting_run(client)
            key = f"idempotent-{run_id}-round-1"
            first = self._answer(client, run_id, pending, idempotency_key=key)
            second = self._answer(client, run_id, pending, idempotency_key=key)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(second.status_code, 202)
            self.assertTrue(second.json()["replayed"])
            with SessionLocal() as db:
                count = db.scalar(
                    select(func.count())
                    .select_from(AgentClarification)
                    .where(AgentClarification.run_id == run_id)
                )
            self.assertEqual(count, 1)

    def test_three_round_limit_prevents_infinite_clarification_loop(self) -> None:
        unresolved = CaseAnalysisOutcome(
            facts=CaseFacts(
                case_type="合同纠纷",
                key_facts=["交付事实仍不完整"],
                missing_information=["关键履行时间"],
                questions_for_user=["请补充关键履行时间。"],
            ),
            source="rules",
        )
        with (
            patch(
                "app.workflows.legal_report_graph.analyze_case_agent",
                return_value=unresolved,
            ),
            TestClient(app) as client,
        ):
            created = client.post(
                "/api/v1/runs",
                data={"question": "合同履行情况不明，应如何处理？", "mode": "offline"},
            )
            run_id = created.json()["run_id"]
            for round_number in range(1, 4):
                pending = client.get(f"/api/v1/runs/{run_id}/pending-action").json()
                self.assertEqual(pending["action"]["round"], round_number)
                submitted = self._answer(
                    client,
                    run_id,
                    pending,
                    idempotency_key=f"bounded-{run_id}-round-{round_number}",
                    answer="目前仍无法确认",
                )
                self.assertEqual(submitted.status_code, 202)
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "waiting_for_approval")
            self.assertEqual(self._approve(client, run_id).status_code, 202)
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["clarification_round"], 3)
            self.assertEqual(
                client.get(f"/api/v1/runs/{run_id}/pending-action").json()["action"],
                None,
            )


if __name__ == "__main__":
    unittest.main()
