import json
from dataclasses import dataclass

from app.llm import LLMClientError, OpenAICompatibleLLM
from app.schemas import CaseFacts
from app.services.case_analyzer import analyze_case


@dataclass(frozen=True)
class CaseAnalysisOutcome:
    facts: CaseFacts
    source: str
    fallback_reason: str | None = None


SYSTEM_PROMPT = """你是案件事实抽取组件。只能依据用户提供的文本，不得补充未出现的事实。
返回一个 JSON 对象，字段必须为：case_type、parties、key_facts、claims、dispute_focuses、confidence、missing_information、questions_for_user。
列表字段没有内容时返回空列表。confidence 为 0 到 1。不要输出 Markdown。"""


def analyze_case_agent(text: str, question: str, llm: OpenAICompatibleLLM | None) -> CaseAnalysisOutcome:
    if llm is None:
        return CaseAnalysisOutcome(analyze_case(text, question), "rules")
    user_prompt = json.dumps(
        {"document_text": text[:30000], "question": question},
        ensure_ascii=False,
    )
    try:
        facts = llm.invoke_structured(SYSTEM_PROMPT, user_prompt, CaseFacts)
        return CaseAnalysisOutcome(facts, "llm")
    except LLMClientError as error:
        return CaseAnalysisOutcome(analyze_case(text, question), "rules_fallback", f"{error.code}: {error}")

