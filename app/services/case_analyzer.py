import re

from app.schemas import CaseFacts


def analyze_case(text: str, question: str) -> CaseFacts:
    """第一周确定性基线；第二周替换为带 Schema 校验的 LLM 抽取。"""
    combined = f"{text}\n{question}".strip()
    if "劳动" in combined or "工资" in combined or "加班" in combined:
        case_type = "劳动争议"
    elif "合同" in combined or "违约" in combined or "货款" in combined:
        case_type = "合同纠纷"
    else:
        case_type = "民事纠纷"

    party_pattern = r"(?:原告|被告|申请人|被申请人|甲方|乙方)[：: ]*([^，。；\n]{2,30})"
    parties = list(dict.fromkeys(re.findall(party_pattern, combined)))
    sentences = [part.strip() for part in re.split(r"[。；\n]", combined) if part.strip()]
    claims = [part for part in sentences if any(word in part for word in ("请求", "赔偿", "支付", "返还", "解除"))][:5]
    focuses = [part for part in sentences if any(word in part for word in ("争议", "是否", "违约", "责任", "解除"))][:5]
    return CaseFacts(
        case_type=case_type,
        parties=parties,
        key_facts=sentences[:8],
        claims=claims,
        dispute_focuses=focuses,
    )

