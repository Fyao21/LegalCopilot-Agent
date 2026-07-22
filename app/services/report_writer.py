import json

from app.llm import LLMClientError, OpenAICompatibleLLM
from app.schemas import CaseFacts, ReportDraft, ReviewedCitation

SYSTEM_PROMPT = """你是法律分析报告写作组件。只允许使用输入中的案件事实和已审核法规，不得编造新法条、案号或事实。
返回 JSON：title、analysis、suggestions、evidence_gaps。analysis 中引用条文时只使用 [article_id] 格式。不要输出 Markdown 代码块。"""


def create_report_draft(
    facts: CaseFacts,
    citations: list[ReviewedCitation],
    llm: OpenAICompatibleLLM | None,
) -> tuple[ReportDraft, str | None]:
    verified = [citation for citation in citations if citation.verified]
    fallback_reason: str | None
    if llm is not None and verified:
        payload = {
            "facts": facts.model_dump(),
            "verified_citations": [citation.model_dump() for citation in verified],
        }
        try:
            return llm.invoke_structured(
                SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), ReportDraft
            ), None
        except LLMClientError as error:
            fallback_reason = f"{error.code}: {error}"
    else:
        fallback_reason = None if llm is None else "没有通过审核的引用"

    citation_summary = (
        "；".join(
            f"依据 [{citation.article_id}] {citation.law_name}{citation.article_number}"
            for citation in verified
        )
        or "当前知识库没有找到足够可信的直接依据"
    )
    analysis = (
        f"本案初步识别为{facts.case_type}。"
        f"当前争议焦点包括：{'；'.join(facts.dispute_focuses) or '材料信息不足，尚未形成明确争议焦点'}。"
        f"{citation_summary}。结论仍需结合合同原件、履行凭证及权威法律来源进一步核验。"
    )
    draft = ReportDraft(
        title=f"{facts.case_type}法律分析报告",
        analysis=analysis,
        suggestions=[
            "补充能够证明案件事实的原始材料",
            "核对引用条文的现行有效版本",
            "复杂案件应咨询具备资质的法律专业人士",
        ],
        evidence_gaps=facts.missing_information or ["当前仅依据用户提交材料，证据完整性尚未核验"],
    )
    return draft, fallback_reason


def render_markdown(draft: ReportDraft, facts: CaseFacts, citations: list[ReviewedCitation]) -> str:
    lines = [
        f"# {draft.title}",
        "",
        "> 本报告仅用于技术演示，不构成法律意见。法规内容应以权威来源的现行有效文本为准。",
        "",
        "## 一、案件摘要",
        "",
        f"- 案件类型：{facts.case_type}",
        f"- 当事人：{'、'.join(facts.parties) or '材料未明确'}",
        f"- 关键事实：{'；'.join(facts.key_facts) or '材料不足'}",
        f"- 诉求：{'；'.join(facts.claims) or '材料未明确'}",
        "",
        "## 二、争议焦点",
        "",
        *(f"{index}. {focus}" for index, focus in enumerate(facts.dispute_focuses, 1)),
        "",
        "## 三、法律分析",
        "",
        draft.analysis,
        "",
        "## 四、行动建议",
        "",
        *(f"- {suggestion}" for suggestion in draft.suggestions),
        "",
        "## 五、证据与信息缺口",
        "",
        *(f"- {gap}" for gap in draft.evidence_gaps),
        "",
        "## 六、审核通过的法律依据",
        "",
    ]
    verified = [citation for citation in citations if citation.verified]
    if not verified:
        lines.append("当前没有通过审核的法律引用，报告结论为低置信度。")
    for citation in verified:
        lines.extend(
            [
                f"### [{citation.article_id}] {citation.law_name} {citation.article_number}",
                "",
                citation.excerpt,
                "",
                f"来源：{citation.source}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"
