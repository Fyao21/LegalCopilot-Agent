import unittest
from typing import TypeVar
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import app
from app.services.embedding_provider import HashEmbeddingProvider

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeNormalizerLLM:
    model = "test-normalizer"

    def invoke_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        return schema.model_validate(
            {
                "law_name": "中华人民共和国食品安全法",
                "article_number": "第四条",
                "source": "国家法律法规数据库",
                "content": "食品生产经营者对其生产经营食品的安全负责。",
                "confidence": 0.95,
                "warnings": [],
                "multiple_articles_detected": False,
            }
        )


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.embedding_patcher = patch(
            "app.services.retrieval_service.get_embedding_provider",
            return_value=HashEmbeddingProvider(),
        )
        self.embedding_patcher.start()

    def tearDown(self) -> None:
        self.embedding_patcher.stop()

    def test_health_and_seed_data(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")
            self.assertGreaterEqual(response.json()["article_count"], 10)

    def test_random_question_examples_support_count_and_category(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/examples/questions/random",
                params={
                    "count": 5,
                    "category": "食品安全",
                    "detail_level": "detailed",
                },
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["count"], 5)
            self.assertEqual(body["requested_category"], "食品安全")
            self.assertEqual(body["requested_detail_level"], "detailed")
            self.assertIn("食品安全", body["available_categories"])
            self.assertEqual(len({item["example_id"] for item in body["examples"]}), 5)
            self.assertTrue(all(item["category"] == "食品安全" for item in body["examples"]))
            self.assertTrue(all(item["detail_level"] == "detailed" for item in body["examples"]))
            self.assertTrue(all(len(item["question"]) > 180 for item in body["examples"]))

    def test_random_question_examples_reject_unknown_category(self) -> None:
        response = TestClient(app).get(
            "/api/v1/examples/questions/random",
            params={"category": "不存在的分类"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("可选值", response.json()["detail"])

        invalid_detail = TestClient(app).get(
            "/api/v1/examples/questions/random",
            params={"detail_level": "very-detailed"},
        )
        self.assertEqual(invalid_detail.status_code, 422)

    def test_article_search(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/articles/search",
                json={"query": "合同不履行如何承担违约责任", "limit": 3},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 3)
            self.assertEqual(response.headers["X-Embedding-Provider"], "hash")
            self.assertEqual(response.headers["X-Embedding-Model"], "chinese-bigram-sha256-v1")

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

    def test_create_knowledge_article_is_immediately_searchable_and_rejects_duplicate(self) -> None:
        suffix = uuid4().hex[:8]
        payload = {
            "law_name": f"测试法规{suffix}",
            "article_number": "第一条",
            "content": f"知识库接口测试专用条文{suffix}，用于验证新增后能够立即检索。",
            "source": "自动化测试数据，不属于真实法律条文",
        }
        with TestClient(app) as client:
            created = client.post("/api/v1/knowledge/articles", json=payload)
            self.assertEqual(created.status_code, 201)
            article_id = created.json()["article_id"]

            duplicate = client.post("/api/v1/knowledge/articles", json=payload)
            self.assertEqual(duplicate.status_code, 409)

            search = client.post(
                "/api/v1/articles/search",
                json={"query": f"知识库接口测试专用条文{suffix}", "limit": 5},
            )
            self.assertEqual(search.status_code, 200)
            self.assertIn(article_id, [item["article_id"] for item in search.json()])

            detail = client.get(f"/api/v1/articles/{article_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["source"], payload["source"])

    def test_create_knowledge_article_rejects_blank_fields(self) -> None:
        response = TestClient(app).post(
            "/api/v1/knowledge/articles",
            json={
                "law_name": "  ",
                "article_number": "第一条",
                "content": "有效内容",
                "source": "测试来源",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_batch_knowledge_upload_returns_per_file_results(self) -> None:
        suffix = uuid4().hex[:8]
        law_name = f"批量测试法规{suffix}"
        valid_text = (
            f"{law_name}\n第一条\n自动化测试来源\n批量知识库测试正文{suffix}，用于验证解析、入库和索引。"
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/knowledge/articles/batch",
                files=[
                    ("files", ("valid.txt", valid_text.encode("utf-8"), "text/plain")),
                    ("files", ("duplicate.txt", valid_text.encode("utf-8"), "text/plain")),
                    ("files", ("invalid.txt", "只有一行".encode(), "text/plain")),
                ],
            )

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["total"], 3)
            self.assertEqual(body["created_count"], 1)
            self.assertEqual(body["duplicate_count"], 1)
            self.assertEqual(body["invalid_count"], 1)
            self.assertEqual(
                [item["status"] for item in body["items"]],
                ["created", "duplicate", "invalid"],
            )
            article_id = body["items"][0]["article_id"]
            detail = client.get(f"/api/v1/articles/{article_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertIn(suffix, detail.json()["content"])

    def test_agent_normalizes_unstructured_txt_without_writing_database(self) -> None:
        raw = (
            "【法规资料】\n法律名称=中华人民共和国食品安全法\n"
            "条号写的是第四条\n来源：国家法律法规数据库\n"
            "正文开始\n食品生产经营者对其生产经营食品的安全负责。"
        )
        with patch("app.main.get_llm_client", return_value=FakeNormalizerLLM()):
            response = TestClient(app).post(
                "/api/v1/knowledge/articles/normalize",
                files={"file": ("messy law.txt", raw.encode("utf-8"), "text/plain")},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ready_for_import"])
        self.assertTrue(body["requires_human_review"])
        self.assertEqual(body["model"], "test-normalizer")
        self.assertEqual(body["standardized_text"].splitlines()[0], "中华人民共和国食品安全法")
        self.assertEqual(body["standardized_text"].splitlines()[1], "第四条")

    def test_agent_normalizer_requires_online_llm_and_txt(self) -> None:
        with patch("app.main.get_llm_client", return_value=None):
            unavailable = TestClient(app).post(
                "/api/v1/knowledge/articles/normalize",
                files={"file": ("messy.txt", "任意法规文本".encode(), "text/plain")},
            )
        unsupported = TestClient(app).post(
            "/api/v1/knowledge/articles/normalize",
            files={"file": ("messy.pdf", b"%PDF", "application/pdf")},
        )

        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("在线模型", unavailable.json()["detail"])
        self.assertEqual(unsupported.status_code, 415)

    def test_offline_agent_workflow_and_report(self) -> None:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/runs",
                data={
                    "question": (
                        "合同约定交货日期为2026年6月30日，供应商收取货款后仍未交货，"
                        "我能否解除合同并要求赔偿？"
                    ),
                    "mode": "offline",
                },
            )
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run_id"]
            self.assertEqual(created.json()["status"], "queued")

            status = client.get(f"/api/v1/runs/{run_id}")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "waiting_for_approval")
            self.assertEqual(status.json()["progress"], 97)
            self.assertIsNotNone(status.json()["started_at"])
            self.assertIsNone(status.json()["completed_at"])
            nodes = [trace["node"] for trace in status.json()["traces"]]
            self.assertEqual(nodes[:3], ["analyze_case", "retrieve_laws", "review_citations"])
            self.assertEqual(nodes[-1], "write_report")

            citations = client.get(f"/api/v1/runs/{run_id}/citations")
            self.assertEqual(citations.status_code, 200)
            self.assertTrue(any(item["verified"] for item in citations.json()))

            report = client.get(f"/api/v1/runs/{run_id}/report")
            self.assertEqual(report.status_code, 200)
            self.assertFalse(report.json()["is_final"])
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
        with (
            patch("app.workflows.legal_report_graph.get_llm_client", return_value=None),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/runs",
                data={"question": "公司拖欠工资并且没有签书面劳动合同", "mode": "agent"},
            )
            self.assertEqual(response.status_code, 202)
            run_id = response.json()["run_id"]
            status = client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(status["status"], "waiting_for_approval")
            self.assertEqual(status["facts"]["case_type"], "劳动争议")
            self.assertEqual(status["execution_engine"], "fallback")
            self.assertEqual(status["model"], "offline-template")


if __name__ == "__main__":
    unittest.main()
