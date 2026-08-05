import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.database import SessionLocal
from app.llm.client import OpenAICompatibleLLM
from app.main import app
from app.models import AgentRun
from app.services.observability import estimate_cost_cny, sanitize_span_attributes


class _UsageResult(BaseModel):
    answer: str


class EighthWeekObservabilityTests(unittest.TestCase):
    question = (
        "合同约定供应商收到全部货款后7日内交货，我方已于2026年1月3日支付20万元，"
        "但对方逾期30日仍未交货。我方已书面催告并保留付款凭证、合同和聊天记录，"
        "现要求解除合同、返还货款并赔偿另行采购产生的3万元差价。"
    )

    @classmethod
    def setUpClass(cls) -> None:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/runs",
                data={"question": cls.question, "mode": "offline"},
            )
            cls.created_status_code = created.status_code
            cls.created_headers = dict(created.headers)
            cls.created = created.json()
            cls.run_id = cls.created["run_id"]
            cls.status_response = client.get(f"/api/v1/runs/{cls.run_id}")
            cls.monitoring_response = client.get(f"/api/v1/runs/{cls.run_id}/monitoring")

    def test_create_and_status_expose_trace_navigation(self) -> None:
        self.assertEqual(self.created_status_code, 202)
        self.assertRegex(self.created["trace_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(
            self.created["monitoring_url"],
            f"/api/v1/runs/{self.run_id}/monitoring",
        )
        self.assertRegex(self.created_headers["x-trace-id"], r"^[0-9a-f]{32}$")
        self.assertEqual(self.created_headers["x-trace-id"], self.created["trace_id"])
        status = self.status_response.json()
        self.assertEqual(status["trace_id"], self.created["trace_id"])
        self.assertIn("total_duration_ms", status)
        self.assertIn("estimated_cost_cny", status)
        self.assertNotIn("estimated_cost_usd", status)
        self.assertIn("fallback_count", status)

    def test_run_monitoring_contains_root_nodes_and_embedding_span(self) -> None:
        self.assertEqual(self.monitoring_response.status_code, 200)
        detail = self.monitoring_response.json()
        self.assertEqual(detail["trace_id"], self.created["trace_id"])
        self.assertIn("estimated_cost_cny", detail)
        self.assertNotIn("estimated_cost_usd", detail)
        names = {span["name"] for span in detail["spans"]}
        self.assertIn("agent.invoke", names)
        self.assertIn("agent.analyze_case", names)
        self.assertIn("agent.retrieval", names)
        self.assertIn("gen_ai.embeddings", names)
        self.assertGreaterEqual(detail["total_duration_ms"], 0)
        self.assertIsNotNone(detail["slowest_node"])

    def test_monitoring_overview_aggregates_runs_and_validates_window(self) -> None:
        with TestClient(app) as client:
            overview = client.get("/api/v1/monitoring/overview?days=7")
            invalid = client.get("/api/v1/monitoring/overview?days=91")
        self.assertEqual(overview.status_code, 200)
        payload = overview.json()
        self.assertGreaterEqual(payload["run_count"], 1)
        self.assertTrue(any(run["run_id"] == self.run_id for run in payload["recent_runs"]))
        self.assertTrue(any(metric["node"] == "analyze_case" for metric in payload["node_metrics"]))
        self.assertEqual(invalid.status_code, 422)

    def test_span_attribute_allowlist_rejects_case_and_secret_content(self) -> None:
        secret = "sk-test-do-not-persist"
        safe = sanitize_span_attributes(
            {
                "run.id": self.run_id,
                "agent.mode": "agent",
                "question": self.question,
                "document.text": "身份证号和家庭住址",
                "api_key": secret,
                "gen_ai.request.model": "test-model",
            }
        )
        serialized = repr(safe)
        self.assertEqual(safe["run.id"], self.run_id)
        self.assertEqual(safe["agent.mode"], "agent")
        self.assertEqual(safe["gen_ai.request.model"], "test-model")
        self.assertNotIn(self.question, serialized)
        self.assertNotIn(secret, serialized)
        self.assertNotRegex(serialized.lower(), re.compile(r"api[_-]?key|document\\.text"))

    def test_cost_estimation_uses_configured_per_million_rates(self) -> None:
        settings = SimpleNamespace(
            llm_input_cost_per_million_cny=2.0,
            llm_output_cost_per_million_cny=6.0,
            embedding_cost_per_million_cny=0.5,
        )
        with patch("app.services.observability.get_settings", return_value=settings):
            chat_cost = estimate_cost_cny(input_tokens=1_000, output_tokens=500)
            embedding_cost = estimate_cost_cny(input_tokens=2_000, operation="embedding")
        self.assertEqual(chat_cost, 0.005)
        self.assertEqual(embedding_cost, 0.001)

    def test_llm_usage_prefers_provider_token_counts(self) -> None:
        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                    "usage": {"prompt_tokens": 123, "completion_tokens": 45},
                }

        class FakeClient:
            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def post(self, *_args, **_kwargs):
                return FakeResponse()

        llm = OpenAICompatibleLLM("test-key", "https://example.test/v1", "test-model")
        with patch("app.llm.client.httpx.Client", FakeClient):
            result = llm.invoke_structured("system", "user", _UsageResult)
        usage = llm.usage_snapshot()
        self.assertEqual(result.answer, "ok")
        self.assertEqual(usage.input_tokens, 123)
        self.assertEqual(usage.output_tokens, 45)
        self.assertEqual(usage.request_count, 1)
        self.assertEqual(usage.retry_count, 0)

    def test_legacy_run_without_trace_returns_clear_404(self) -> None:
        with SessionLocal() as db:
            legacy = AgentRun(
                question="历史任务",
                extracted_text="",
                mode="offline",
                trace_id=None,
            )
            db.add(legacy)
            db.commit()
            db.refresh(legacy)
            legacy_id = legacy.id
        with TestClient(app) as client:
            response = client.get(f"/api/v1/runs/{legacy_id}/monitoring")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "该运行没有可观测性数据")


if __name__ == "__main__":
    unittest.main()
