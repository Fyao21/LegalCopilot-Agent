import re

from app.schemas import CaseFacts


def analyze_case(text: str, question: str) -> CaseFacts:
    """第一周确定性基线；第二周替换为带 Schema 校验的 LLM 抽取。"""
    combined = f"{text}\n{question}".strip()
    labor_terms = (
        "劳动",
        "工资",
        "加班",
        "用人单位",
        "员工",
        "入职",
        "排班",
        "经济补偿",
        "欠薪",
    )
    contract_terms = (
        "合同",
        "违约",
        "货款",
        "采购",
        "供应商",
        "交付",
        "履行",
        "卖方",
        "买方",
        "承揽",
        "委托",
        "承运",
        "合作约定",
    )
    if any(term in combined for term in labor_terms):
        case_type = "劳动争议"
    elif any(term in combined for term in contract_terms):
        case_type = "合同纠纷"
    else:
        case_type = "民事纠纷"

    party_pattern = r"(?:原告|被告|申请人|被申请人|甲方|乙方)[：: ]*([^，。；\n]{2,30})"
    parties = list(dict.fromkeys(re.findall(party_pattern, combined)))
    sentences = [part.strip() for part in re.split(r"[。；\n]", combined) if part.strip()]
    claims = [
        part
        for part in sentences
        if any(word in part for word in ("请求", "赔偿", "支付", "返还", "解除", "补偿", "工资"))
    ][:5]
    focuses = [
        part
        for part in sentences
        if any(
            word in part
            for word in ("争议", "是否", "违约", "责任", "解除", "赔偿", "补偿", "工资", "义务", "二倍")
        )
    ][:5]
    return CaseFacts(
        case_type=case_type,
        parties=parties,
        key_facts=sentences[:8],
        claims=claims,
        dispute_focuses=focuses,
    )
