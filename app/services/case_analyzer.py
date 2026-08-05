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
    food_safety_terms = (
        "食物中毒",
        "食品安全",
        "食品变质",
        "过期食品",
        "餐馆",
        "饭店",
        "餐饮",
        "外卖",
        "用餐",
        "就餐",
    )
    consumer_terms = (
        "消费者",
        "商家",
        "经营者",
        "退款",
        "退货",
        "商品",
        "产品质量",
        "虚假宣传",
        "欺诈",
    )
    tort_terms = (
        "人身损害",
        "受伤",
        "医疗费",
        "侵权",
        "精神损害",
        "财产损失",
    )
    if any(term in combined for term in labor_terms):
        case_type = "劳动争议"
    elif any(term in combined for term in food_safety_terms):
        case_type = "食品安全与消费者权益纠纷"
    elif any(term in combined for term in consumer_terms):
        case_type = "消费者权益纠纷"
    elif any(term in combined for term in contract_terms):
        case_type = "合同纠纷"
    elif any(term in combined for term in tort_terms):
        case_type = "侵权责任纠纷"
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
            for word in (
                "争议",
                "是否",
                "违约",
                "责任",
                "负责",
                "解除",
                "赔偿",
                "补偿",
                "退款",
                "工资",
                "义务",
                "二倍",
            )
        )
    ][:5]
    missing_information: list[str] = []
    questions_for_user: list[str] = []
    unknown_markers = ("暂不清楚", "不知道交货日期", "未约定交货日期", "没有约定交货日期")
    has_unknown_delivery_date = any(marker in combined for marker in unknown_markers)
    has_delivery_date = bool(
        re.search(
            r"(?:交货|交付|发货)(?:日期|时间|期限)?[^。\n]{0,12}"
            r"(?:20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?|"
            r"\d{1,2}月\d{1,2}日|"
            r"\d+\s*(?:日|天|个工作日|个月|周)(?:内|后|前)?)",
            combined,
        )
    )
    delivery_dispute = case_type == "合同纠纷" and any(
        term in combined for term in ("交货", "交付", "发货", "没有货", "未履行")
    )
    if delivery_dispute and not has_delivery_date and not has_unknown_delivery_date:
        missing_information.append("约定交货日期或履行期限")
        questions_for_user.append("合同约定的交货日期或履行期限是什么？如果没有约定，可以回答“暂不清楚”。")
    return CaseFacts(
        case_type=case_type,
        parties=parties,
        key_facts=sentences[:8],
        claims=claims,
        dispute_focuses=focuses,
        missing_information=missing_information,
        questions_for_user=questions_for_user,
    )
