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
case_type 必须是非空字符串；无法判断时返回“未识别”，不能返回空字符串或只包含空格。
优先从以下类别中选择最具体的一项：劳动争议、合同纠纷、食品安全与消费者权益纠纷、消费者权益纠纷、侵权责任纠纷、民事纠纷。
例如“食物中毒商家是否负责”应识别为“食品安全与消费者权益纠纷”，不能因为描述较短就返回“未识别”。
用户补充内容会以“问题/用户回答”形式附在材料末尾。已经回答的信息（包括“暂不清楚”）
不得再次列入 missing_information 或 questions_for_user，只有新的关键缺口才能继续追问。
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
        if facts.case_type == "未识别":
            baseline = analyze_case(text, question)
            facts = facts.model_copy(
                update={
                    "case_type": baseline.case_type,
                    "key_facts": facts.key_facts or baseline.key_facts,
                    "claims": facts.claims or baseline.claims,
                    "dispute_focuses": facts.dispute_focuses or baseline.dispute_focuses,
                }
            )
            return CaseAnalysisOutcome(
                facts,
                "llm_enriched",
                "LLM 返回未识别，已使用本地分类器补全案件类型",
            )
        return CaseAnalysisOutcome(facts, "llm")
    except LLMClientError as error:
        return CaseAnalysisOutcome(analyze_case(text, question), "rules_fallback", f"{error.code}: {error}")
