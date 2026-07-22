import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMClientError, OpenAICompatibleLLM
from app.models import LegalArticle
from app.schemas import Citation, CitationReviewBatch, ReviewedCitation
from app.services.embeddings import tokenize


def review_citations(
    db: Session,
    citations: list[Citation],
    query: str,
    llm: OpenAICompatibleLLM | None = None,
) -> list[ReviewedCitation]:
    article_ids = [citation.article_id for citation in citations]
    rows = (
        db.scalars(select(LegalArticle).where(LegalArticle.id.in_(article_ids))).all() if article_ids else []
    )
    articles = {article.id: article for article in rows}
    query_tokens = set(tokenize(query))
    reviewed: list[ReviewedCitation] = []
    for citation in citations:
        article = articles.get(citation.article_id)
        exact = bool(
            article
            and article.law_name == citation.law_name
            and article.article_number == citation.article_number
            and article.content == citation.excerpt
        )
        support_overlap = (
            len(query_tokens & set(tokenize(article.content))) if article and query_tokens else 0
        )
        verified = exact and (citation.score >= 0.03 or support_overlap > 0)
        if not exact:
            status, reason = "rejected", "引用字段与知识库原文不一致"
        elif verified:
            status, reason = "verified", "条文 ID、名称、条号和原文一致，且与查询存在检索关联"
        else:
            status, reason = "low_confidence", "条文真实，但与当前问题的支撑关系较弱"
        reviewed.append(
            ReviewedCitation(
                **citation.model_dump(),
                review_status=status,
                review_reason=reason,
                verified=verified,
            )
        )
    if llm is None:
        return reviewed

    deterministic_verified = [citation for citation in reviewed if citation.verified]
    if not deterministic_verified:
        return reviewed
    system_prompt = """判断每条法规是否能够支撑用户问题。只能审核给定 article_id，不得创造新条文。
返回 JSON：{\"reviews\":[{\"article_id\":1,\"supported\":true,\"reason\":\"理由\"}]}。不要输出其他内容。"""
    payload = {
        "query": query,
        "citations": [
            {
                "article_id": item.article_id,
                "law_name": item.law_name,
                "article_number": item.article_number,
                "content": item.excerpt,
            }
            for item in deterministic_verified
        ],
    }
    try:
        decision = llm.invoke_structured(
            system_prompt, json.dumps(payload, ensure_ascii=False), CitationReviewBatch
        )
    except LLMClientError:
        return reviewed
    allowed_ids = {item.article_id for item in deterministic_verified}
    decisions = {item.article_id: item for item in decision.reviews if item.article_id in allowed_ids}
    output: list[ReviewedCitation] = []
    for citation in reviewed:
        semantic = decisions.get(citation.article_id)
        if citation.verified and semantic is not None and not semantic.supported:
            citation = citation.model_copy(
                update={
                    "verified": False,
                    "review_status": "low_confidence",
                    "review_reason": f"语义审核未通过：{semantic.reason}",
                }
            )
        elif citation.verified and semantic is not None:
            citation = citation.model_copy(
                update={"review_reason": f"确定性校验通过；语义审核通过：{semantic.reason}"}
            )
        output.append(citation)
    return output
