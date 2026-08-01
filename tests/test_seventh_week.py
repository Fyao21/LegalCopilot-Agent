import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import AgentRunCitation, Law, LawVersion, LegalArticle
from app.services.embedding_provider import HashEmbeddingProvider
from app.services.mixed_retriever import retrieve_articles_mixed


class SeventhWeekLawVersionTests(unittest.TestCase):
    transition_query = (
        "中华人民共和国合同法第九十四条 中华人民共和国民法典第五百六十三条 迟延履行 催告 解除合同"
    )

    @classmethod
    def setUpClass(cls) -> None:
        with TestClient(app):
            pass

    def _retrieve(self, target: date | None):
        with SessionLocal() as db:
            return retrieve_articles_mixed(
                db,
                self.transition_query,
                HashEmbeddingProvider(),
                limit=10,
                as_of_date=target,
            )

    def test_transition_versions_are_related_and_use_half_open_dates(self) -> None:
        with SessionLocal() as db:
            contract_law = db.scalar(select(Law).where(Law.name == "中华人民共和国合同法"))
            civil_code = db.scalar(select(Law).where(Law.name == "中华人民共和国民法典"))
            self.assertIsNotNone(contract_law)
            self.assertIsNotNone(civil_code)
            historical = db.scalar(
                select(LawVersion).where(
                    LawVersion.law_id == contract_law.id,
                    LawVersion.version_label == "1999年施行版本",
                )
            )
            current = db.scalar(
                select(LawVersion).where(
                    LawVersion.law_id == civil_code.id,
                    LawVersion.effective_to.is_(None),
                )
            )
            self.assertEqual(historical.effective_from, date(1999, 10, 1))
            self.assertEqual(historical.effective_to, date(2021, 1, 1))
            self.assertEqual(historical.status, "repealed")
            self.assertEqual(current.effective_from, date(2021, 1, 1))
            self.assertEqual(current.supersedes_version_id, historical.id)

    def test_day_before_boundary_returns_historical_contract_law(self) -> None:
        result = self._retrieve(date(2020, 12, 31))
        identities = {(item.law_name, item.article_number) for item in result.citations}
        historical = next(
            item
            for item in result.citations
            if item.law_name == "中华人民共和国合同法" and item.article_number == "第九十四条"
        )
        self.assertIn(("中华人民共和国合同法", "第九十四条"), identities)
        self.assertNotIn(("中华人民共和国民法典", "第五百六十三条"), identities)
        self.assertEqual(historical.version_label, "1999年施行版本")
        self.assertEqual(historical.effect_status, "repealed")
        self.assertEqual(result.as_of_date, date(2020, 12, 31))

    def test_boundary_day_switches_to_current_civil_code(self) -> None:
        result = self._retrieve(date(2021, 1, 1))
        identities = {(item.law_name, item.article_number) for item in result.citations}
        current = next(
            item
            for item in result.citations
            if item.law_name == "中华人民共和国民法典" and item.article_number == "第五百六十三条"
        )
        self.assertIn(("中华人民共和国民法典", "第五百六十三条"), identities)
        self.assertNotIn(("中华人民共和国合同法", "第九十四条"), identities)
        self.assertEqual(current.effect_status, "effective")
        self.assertEqual(current.effective_from, date(2021, 1, 1))

    def test_omitted_date_remains_compatible_and_excludes_repealed_article(self) -> None:
        result = self._retrieve(None)
        identities = {(item.law_name, item.article_number) for item in result.citations}
        self.assertEqual(result.as_of_date, date.today())
        self.assertNotIn(("中华人民共和国合同法", "第九十四条"), identities)
        self.assertIn(("中华人民共和国民法典", "第五百六十三条"), identities)

    def test_search_api_accepts_date_and_exposes_applied_date_header(self) -> None:
        with (
            patch(
                "app.services.retrieval_service.get_embedding_provider",
                return_value=HashEmbeddingProvider(),
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/articles/search",
                json={
                    "query": self.transition_query,
                    "limit": 10,
                    "as_of_date": "2020-12-31",
                },
            )
            invalid = client.post(
                "/api/v1/articles/search",
                json={
                    "query": self.transition_query,
                    "limit": 5,
                    "as_of_date": "2020-13-40",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Law-As-Of-Date"], "2020-12-31")
        self.assertEqual(response.json()[0]["law_name"], "中华人民共和国合同法")
        self.assertIsInstance(response.json()[0]["law_version_id"], int)
        self.assertEqual(invalid.status_code, 422)

    def test_agent_persists_selected_version_in_citations_and_report(self) -> None:
        question = (
            "合同约定供应商应在收到全部货款后7日内交货，现已过去30日仍未交货，"
            "我要求解除合同、退还货款并赔偿损失。请结合中华人民共和国合同法第九十四条"
            "和中华人民共和国民法典第五百六十三条分析。"
        )
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/runs",
                data={
                    "question": question,
                    "mode": "offline",
                    "as_of_date": "2020-12-31",
                },
            )
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run_id"]
            status = client.get(f"/api/v1/runs/{run_id}")
            citations = client.get(f"/api/v1/runs/{run_id}/citations")
            report = client.get(f"/api/v1/runs/{run_id}/report")

        self.assertEqual(status.json()["as_of_date"], "2020-12-31")
        self.assertEqual(status.json()["status"], "waiting_for_approval")
        historical = next(item for item in citations.json() if item["law_name"] == "中华人民共和国合同法")
        self.assertEqual(historical["version_label"], "1999年施行版本")
        self.assertEqual(report.json()["as_of_date"], "2020-12-31")
        self.assertIn("法规检索时点：2020-12-31", report.json()["markdown"])
        self.assertIn("1999年施行版本", report.json()["markdown"])
        with SessionLocal() as db:
            article = db.scalar(
                select(LegalArticle).where(
                    LegalArticle.law_name == "中华人民共和国合同法",
                    LegalArticle.article_number == "第九十四条",
                )
            )
            link = db.scalar(
                select(AgentRunCitation).where(
                    AgentRunCitation.run_id == run_id,
                    AgentRunCitation.article_id == article.id,
                )
            )
            self.assertEqual(link.law_version_id, article.law_version_id)


if __name__ == "__main__":
    unittest.main()
