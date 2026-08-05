import json
import unittest
from datetime import date
from typing import Any

from app.schemas import CaseFacts, ReportDraft, ReportRevision, ReviewedCitation
from app.services.report_writer import create_report_draft, revise_report_markdown


class _CapturingLLM:
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}

    def invoke_structured(self, _system_prompt, user_prompt, schema):
        self.payload = json.loads(user_prompt)
        if schema is ReportDraft:
            return ReportDraft(
                title="食品安全纠纷法律分析报告",
                analysis="根据已审核法规分析。",
                suggestions=["保留证据"],
                evidence_gaps=["因果关系材料"],
            )
        if schema is ReportRevision:
            return ReportRevision(
                markdown="# 修订报告\n\n已根据审批意见修订报告内容。",
                change_summary="补充证据建议",
            )
        raise AssertionError(f"未处理的 Schema：{schema}")


class ReportWriterDateSerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.facts = CaseFacts(
            case_type="食品安全与消费者权益纠纷",
            parties=["消费者", "商家"],
            key_facts=["消费者就餐后身体不适"],
            claims=["要求赔偿"],
            dispute_focuses=["食品与损害之间是否存在因果关系"],
        )
        self.citation = ReviewedCitation(
            article_id=1,
            law_name="中华人民共和国食品安全法",
            article_number="第一百四十八条",
            excerpt="消费者因不符合食品安全标准的食品受到损害的，可以要求赔偿。",
            source="国家法律法规数据库",
            score=0.92,
            version_label="现行有效",
            effect_status="effective",
            effective_from=date(2021, 4, 29),
            effective_to=None,
            review_status="verified",
            review_reason="知识库原文一致",
            verified=True,
        )

    def test_create_report_serializes_law_dates_for_llm_payload(self) -> None:
        llm = _CapturingLLM()

        draft, fallback_reason = create_report_draft(
            self.facts,
            [self.citation],
            llm,  # type: ignore[arg-type]
        )

        citation = llm.payload["verified_citations"][0]
        self.assertEqual(draft.title, "食品安全纠纷法律分析报告")
        self.assertIsNone(fallback_reason)
        self.assertEqual(citation["effective_from"], "2021-04-29")
        self.assertIsNone(citation["effective_to"])

    def test_revise_report_serializes_law_dates_for_llm_payload(self) -> None:
        llm = _CapturingLLM()

        revision, fallback_reason = revise_report_markdown(
            "# 初始报告\n\n初始分析内容。",
            "请补充证据建议",
            2,
            self.facts,
            [self.citation],
            llm,  # type: ignore[arg-type]
        )

        citation = llm.payload["verified_citations"][0]
        self.assertEqual(revision.change_summary, "补充证据建议")
        self.assertIsNone(fallback_reason)
        self.assertEqual(citation["effective_from"], "2021-04-29")
        self.assertIsNone(citation["effective_to"])


if __name__ == "__main__":
    unittest.main()
