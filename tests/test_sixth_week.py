import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import AgentApproval, ReportVersion


class SixthWeekApprovalTests(unittest.TestCase):
    question = (
        "合同约定供应商应在收到全部货款后7日内交货，现已过去30日仍未交货，"
        "我要求解除合同、退还货款并赔偿损失。"
    )

    def _create_draft(self, client: TestClient) -> tuple[int, dict]:
        created = client.post(
            "/api/v1/runs",
            data={"question": self.question, "mode": "offline"},
        )
        self.assertEqual(created.status_code, 202)
        run_id = created.json()["run_id"]
        status = client.get(f"/api/v1/runs/{run_id}").json()
        self.assertEqual(status["status"], "waiting_for_approval")
        self.assertEqual(status["current_report_version"], 1)
        pending = client.get(f"/api/v1/runs/{run_id}/pending-action")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["action"]["type"], "approval")
        return run_id, pending.json()

    def _decide(
        self,
        client: TestClient,
        run_id: int,
        pending: dict,
        action: str,
        *,
        comment: str = "",
        key: str | None = None,
        state_version: int | None = None,
    ):
        return client.post(
            f"/api/v1/runs/{run_id}/approvals",
            headers={
                "Idempotency-Key": key or f"sixth-week-{action}-{run_id}-{pending['action']['action_id']}"
            },
            json={
                "expected_state_version": (
                    pending["state_version"] if state_version is None else state_version
                ),
                "action": action,
                "comment": comment,
                "reviewer": "第六周自动审核人",
            },
        )

    def test_unapproved_draft_is_visible_but_final_export_is_blocked(self) -> None:
        with TestClient(app) as client:
            run_id, _ = self._create_draft(client)
            report = client.get(f"/api/v1/runs/{run_id}/report")
            markdown = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            pdf = client.get(f"/api/v1/runs/{run_id}/export?format=pdf")

            self.assertEqual(report.status_code, 200)
            self.assertEqual(report.json()["approval_status"], "draft")
            self.assertFalse(report.json()["is_final"])
            self.assertEqual(markdown.status_code, 409)
            self.assertEqual(pdf.status_code, 409)
            self.assertIn("尚未通过人工审批", markdown.json()["detail"])

    def test_approve_publishes_exact_version_and_enables_export(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_draft(client)
            approved = self._decide(
                client,
                run_id,
                pending,
                "approve",
                comment="案件事实、引用和风险提示已经核对。",
            )

            self.assertEqual(approved.status_code, 202)
            status = client.get(f"/api/v1/runs/{run_id}").json()
            report = client.get(f"/api/v1/runs/{run_id}/report").json()
            export = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["approved_report_version"], 1)
            self.assertTrue(report["is_final"])
            self.assertEqual(report["approval_status"], "approved")
            self.assertEqual(export.status_code, 200)
            self.assertIn(f"legal-report-{run_id}-v1.md", export.headers["content-disposition"])

    def test_request_changes_creates_version_two_and_preserves_diff(self) -> None:
        with TestClient(app) as client:
            run_id, first_pending = self._create_draft(client)
            requested = self._decide(
                client,
                run_id,
                first_pending,
                "request_changes",
                comment="请把合同解除条件与损失赔偿责任分开说明。",
            )
            self.assertEqual(requested.status_code, 202)

            status = client.get(f"/api/v1/runs/{run_id}").json()
            second_pending = client.get(f"/api/v1/runs/{run_id}/pending-action").json()
            versions = client.get(f"/api/v1/runs/{run_id}/report-versions").json()
            version_two = client.get(f"/api/v1/runs/{run_id}/report-versions/2").json()
            self.assertEqual(status["status"], "waiting_for_approval")
            self.assertEqual(status["current_report_version"], 2)
            self.assertEqual(second_pending["action"]["report_version"], 2)
            self.assertEqual([item["version_number"] for item in versions], [2, 1])
            self.assertEqual(versions[0]["status"], "draft")
            self.assertEqual(versions[1]["status"], "superseded")
            self.assertIn("合同解除条件", version_two["markdown"])
            self.assertIn("--- v1", version_two["diff_from_previous"])
            self.assertIn("+++ v2", version_two["diff_from_previous"])

            approved = self._decide(
                client,
                run_id,
                second_pending,
                "approve",
                comment="第二版已经落实修改意见。",
            )
            self.assertEqual(approved.status_code, 202)
            final_status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(final_status["status"], "completed")
            self.assertEqual(final_status["approved_report_version"], 2)

    def test_reject_ends_run_and_keeps_rejected_draft_for_audit(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_draft(client)
            rejected = self._decide(
                client,
                run_id,
                pending,
                "reject",
                comment="事实材料不足，当前报告不应发布。",
            )

            self.assertEqual(rejected.status_code, 202)
            status = client.get(f"/api/v1/runs/{run_id}").json()
            report = client.get(f"/api/v1/runs/{run_id}/report").json()
            export = client.get(f"/api/v1/runs/{run_id}/export?format=markdown")
            self.assertEqual(status["status"], "rejected")
            self.assertEqual(report["approval_status"], "rejected")
            self.assertFalse(report["is_final"])
            self.assertEqual(export.status_code, 409)

    def test_optimistic_lock_allows_only_one_approval(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_draft(client)
            stale = self._decide(
                client,
                run_id,
                pending,
                "approve",
                state_version=pending["state_version"] - 1,
                key=f"stale-approval-{run_id}",
            )
            first = self._decide(
                client,
                run_id,
                pending,
                "approve",
                key=f"winning-approval-{run_id}",
            )
            second = self._decide(
                client,
                run_id,
                pending,
                "reject",
                comment="并发驳回请求",
                key=f"losing-approval-{run_id}",
            )
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(second.status_code, 409)
            self.assertEqual(client.get(f"/api/v1/runs/{run_id}").json()["status"], "completed")

    def test_duplicate_idempotency_key_does_not_repeat_approval(self) -> None:
        with TestClient(app) as client:
            run_id, pending = self._create_draft(client)
            key = f"approval-idempotent-{run_id}"
            first = self._decide(client, run_id, pending, "approve", key=key)
            second = self._decide(client, run_id, pending, "approve", key=key)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(second.status_code, 202)
            self.assertTrue(second.json()["replayed"])
            with SessionLocal() as db:
                approvals = db.scalar(
                    select(func.count()).select_from(AgentApproval).where(AgentApproval.run_id == run_id)
                )
                versions = db.scalar(
                    select(func.count()).select_from(ReportVersion).where(ReportVersion.run_id == run_id)
                )
            self.assertEqual(approvals, 1)
            self.assertEqual(versions, 1)

    def test_waiting_approval_checkpoint_survives_app_restart(self) -> None:
        with TestClient(app) as first_client:
            run_id, pending = self._create_draft(first_client)

        with TestClient(app) as restarted_client:
            restored = restarted_client.get(f"/api/v1/runs/{run_id}/pending-action")
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(
                restored.json()["action"]["action_id"],
                pending["action"]["action_id"],
            )
            approved = self._decide(
                restarted_client,
                run_id,
                restored.json(),
                "approve",
                comment="重启后审批通过。",
            )
            self.assertEqual(approved.status_code, 202)
            self.assertEqual(
                restarted_client.get(f"/api/v1/runs/{run_id}").json()["status"],
                "completed",
            )


if __name__ == "__main__":
    unittest.main()
