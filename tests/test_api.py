import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiTests(unittest.TestCase):
    def test_health_and_seed_data(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")
            self.assertGreaterEqual(response.json()["article_count"], 10)

    def test_article_search(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/articles/search",
                json={"query": "合同不履行如何承担违约责任", "limit": 3},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 3)

    def test_case_analysis(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/cases",
                data={"question": "对方未按合同交货，我能否请求赔偿？"},
            )
            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertEqual(body["facts"]["case_type"], "合同纠纷")
            self.assertTrue(body["citations"])

    def test_article_detail(self) -> None:
        with TestClient(app) as client:
            search = client.post(
                "/api/v1/articles/search",
                json={"query": "合同违约责任", "limit": 1},
            ).json()
            response = client.get(f"/api/v1/articles/{search[0]['article_id']}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["article_id"], search[0]["article_id"])

    def test_offline_agent_workflow_and_report(self) -> None:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/runs",
                data={
                    "question": "供应商收取货款后没有按合同交货，我能否解除合同并要求赔偿？",
                    "mode": "offline",
                },
            )
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run_id"]
            self.assertEqual(created.json()["status"], "queued")

            status = client.get(f"/api/v1/runs/{run_id}")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["progress"], 100)
            self.assertIsNotNone(status.json()["started_at"])
            self.assertIsNotNone(status.json()["completed_at"])
            nodes = [trace["node"] for trace in status.json()["traces"]]
            self.assertEqual(nodes[:3], ["analyze_case", "retrieve_laws", "review_citations"])
            self.assertEqual(nodes[-1], "write_report")

            citations = client.get(f"/api/v1/runs/{run_id}/citations")
            self.assertEqual(citations.status_code, 200)
            self.assertTrue(any(item["verified"] for item in citations.json()))

            report = client.get(f"/api/v1/runs/{run_id}/report")
            self.assertEqual(report.status_code, 200)
            self.assertIn("本报告仅用于技术演示", report.json()["markdown"])
            self.assertIn("法律依据", report.json()["markdown"])

    def test_completed_run_cannot_retry(self) -> None:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/runs",
                data={"question": "公司拖欠工资如何处理？", "mode": "offline"},
            )
            response = client.post(f"/api/v1/runs/{created.json()['run_id']}/retry")
            self.assertEqual(response.status_code, 409)

    def test_agent_mode_without_key_safely_uses_offline_fallback(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/runs",
                data={"question": "公司拖欠工资并且没有签书面劳动合同", "mode": "agent"},
            )
            self.assertEqual(response.status_code, 202)
            run_id = response.json()["run_id"]
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["facts"]["case_type"], "劳动争议")
            self.assertEqual(status["execution_engine"], "fallback")
            self.assertEqual(status["model"], "offline-template")


if __name__ == "__main__":
    unittest.main()
