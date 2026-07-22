import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base
from app.llm import LLMClientError, OpenAICompatibleLLM
from app.models import AgentRun, LegalArticle
from app.schemas import CaseFacts, Citation
from app.services.case_agent import analyze_case_agent
from app.services.citation_reviewer import review_citations
from app.services.embedding_provider import HashEmbeddingProvider
from app.services.legal_chunker import split_legal_article
from app.services.mixed_retriever import retrieve_articles_mixed
from app.services.seed import seed_sample_laws
from app.workflows import execute_agent_run


class SecondWeekServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_sample_laws(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_mixed_retrieval_exposes_component_scores(self) -> None:
        result = retrieve_articles_mixed(
            self.db,
            "未履行合同应承担什么违约责任",
            HashEmbeddingProvider(),
            limit=3,
        )
        self.assertEqual(len(result.citations), 3)
        self.assertEqual(result.provider, "hash")
        self.assertIsNotNone(result.citations[0].keyword_score)
        self.assertIsNotNone(result.citations[0].semantic_score)
        self.assertGreaterEqual(result.citations[0].score, result.citations[-1].score)

    def test_citation_reviewer_rejects_tampered_text(self) -> None:
        article = self.db.query(LegalArticle).first()
        citation = Citation(
            article_id=article.id,
            law_name=article.law_name,
            article_number=article.article_number,
            excerpt="这是一条被篡改的法条内容",
            source=article.source,
            score=0.9,
            keyword_score=0.9,
            semantic_score=0.9,
        )
        reviewed = review_citations(self.db, [citation], "合同违约")
        self.assertFalse(reviewed[0].verified)
        self.assertEqual(reviewed[0].review_status, "rejected")

    def test_embedding_index_is_idempotent(self) -> None:
        provider = HashEmbeddingProvider()
        first = retrieve_articles_mixed(self.db, "合同责任", provider, limit=1)
        second = retrieve_articles_mixed(self.db, "合同责任", provider, limit=1)
        self.assertEqual(first.citations[0].article_id, second.citations[0].article_id)

    def test_llm_failure_falls_back_to_rules(self) -> None:
        class FailingLLM:
            def invoke_structured(self, *_args, **_kwargs):
                raise LLMClientError("LLM_TIMEOUT", "测试超时", retryable=True)

        outcome = analyze_case_agent("公司拖欠工资", "我可以要求支付工资吗？", FailingLLM())
        self.assertEqual(outcome.source, "rules_fallback")
        self.assertEqual(outcome.facts.case_type, "劳动争议")
        self.assertIn("LLM_TIMEOUT", outcome.fallback_reason)

    def test_empty_knowledge_base_stops_after_bounded_retries(self) -> None:
        empty_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(empty_engine)
        with Session(empty_engine) as empty_db:
            run = AgentRun(question="未知领域问题", extracted_text="没有可用法规", mode="offline")
            empty_db.add(run)
            empty_db.commit()
            empty_db.refresh(run)
            execute_agent_run(empty_db, run)
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.retry_count, 2)
            self.assertIn("低置信度", run.report_markdown)
        empty_engine.dispose()

    def test_long_article_chunking_preserves_article_number(self) -> None:
        text = "第一款内容。" * 100 + "\n" + "第二款内容。" * 100
        chunks = split_legal_article("第一百条", text, max_chars=300, overlap_chars=30)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.article_number == "第一百条" for chunk in chunks))
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))

    def test_invalid_llm_json_is_repaired_once(self) -> None:
        class FakeResponse:
            status_code = 200

            def __init__(self, content: str):
                self.content = content

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": self.content}}]}

        class FakeClient:
            calls = 0

            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def post(self, *_args, **_kwargs):
                FakeClient.calls += 1
                return FakeResponse("not-json" if FakeClient.calls == 1 else '{"case_type":"合同纠纷"}')

        client = OpenAICompatibleLLM("test-key", "https://example.test/v1", "test-model")
        with patch("app.llm.client.httpx.Client", FakeClient):
            result = client.invoke_structured("system", "user", CaseFacts)
        self.assertEqual(result.case_type, "合同纠纷")
        self.assertEqual(FakeClient.calls, 2)

    def test_openai_compatible_environment_aliases(self) -> None:
        values = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "MODEL_NAME": "deepseek-v4-flash",
            "OFFLINE_MODE": "false",
        }
        try:
            with patch.dict(os.environ, values, clear=True):
                get_settings.cache_clear()
                settings = get_settings()
                self.assertEqual(settings.llm_api_key, "test-key")
                self.assertEqual(settings.llm_base_url, "https://api.deepseek.com")
                self.assertEqual(settings.llm_model, "deepseek-v4-flash")
                self.assertFalse(settings.offline_mode)
                self.assertIsNone(settings.embedding_api_key)
        finally:
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
