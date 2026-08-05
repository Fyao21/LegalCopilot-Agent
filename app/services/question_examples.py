import hashlib
import random
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QuestionTemplate:
    category: str
    detail_level: Literal["brief", "detailed"]
    pattern: str
    variables: dict[str, tuple[str, ...]]

    def render(self, rng: random.Random) -> str:
        values = {name: rng.choice(options) for name, options in self.variables.items()}
        return self.pattern.format(**values)


BRIEF_TEMPLATES = (
    QuestionTemplate(
        "劳动争议",
        "brief",
        "{employer}拖欠我{duration}工资，而且{contract}，我可以要求支付工资和补偿吗？",
        {
            "employer": ("公司", "餐馆", "培训机构", "互联网企业"),
            "duration": ("一个月", "两个月", "三个月", "半年"),
            "contract": ("没有签书面劳动合同", "没有缴纳社保", "拒绝提供工资明细"),
        },
    ),
    QuestionTemplate(
        "劳动争议",
        "brief",
        "单位以{reason}为由要求我{action}，这种处理是否合法？",
        {
            "reason": ("业绩不达标", "迟到两次", "试用期不合格", "经营困难"),
            "action": ("立即离职且不给补偿", "接受降薪", "无偿加班", "签署自愿离职书"),
        },
    ),
    QuestionTemplate(
        "合同纠纷",
        "brief",
        "{party}收款后{breach}，我能否{claim}？",
        {
            "party": ("供应商", "装修公司", "培训机构", "承运人", "设备销售商"),
            "breach": ("一直没有交货", "严重延期履行", "交付的产品不符合约定", "拒绝继续履行"),
            "claim": ("解除合同并要求退款赔偿", "要求继续履行并承担违约金", "追回已付款项"),
        },
    ),
    QuestionTemplate(
        "合同纠纷",
        "brief",
        "合同约定{term}，对方现在{behavior}，我应该如何维权？",
        {
            "term": ("月底前完成服务", "验收后七日内付款", "逾期需要支付违约金", "货物必须符合样品"),
            "behavior": ("拒绝履行", "拖延付款", "否认合同效力", "要求单方面变更价格"),
        },
    ),
    QuestionTemplate(
        "食品安全",
        "brief",
        "我在{place}食用{food}后出现{symptom}，商家需要承担什么责任？",
        {
            "place": ("餐馆", "外卖平台购买的店铺", "超市", "夜市摊位"),
            "food": ("海鲜", "熟食", "预包装食品", "饮品"),
            "symptom": ("食物中毒并住院", "呕吐腹泻", "过敏反应", "身体不适并就医"),
        },
    ),
    QuestionTemplate(
        "食品安全",
        "brief",
        "商家销售的食品存在{problem}，我已经{result}，可以要求怎样的赔偿？",
        {
            "problem": ("过期", "发霉", "异物", "标签虚假", "不符合安全标准"),
            "result": ("保留了小票", "拍照并投诉", "食用后就医", "联系商家但被拒绝处理"),
        },
    ),
    QuestionTemplate(
        "消费者权益",
        "brief",
        "我购买的{goods}出现{problem}，商家拒绝{request}，这种情况如何处理？",
        {
            "goods": ("手机", "家用电器", "家具", "健身课程", "旅游服务"),
            "problem": ("反复故障", "与宣传严重不符", "质量问题", "无法正常使用"),
            "request": ("退货退款", "维修或更换", "承担检测费用", "按承诺赔偿"),
        },
    ),
    QuestionTemplate(
        "消费者权益",
        "brief",
        "经营者在销售时{behavior}，导致我支付了{loss}，是否构成欺诈？",
        {
            "behavior": ("隐瞒商品缺陷", "虚构原价", "承诺不存在的功能", "故意提供虚假信息"),
            "loss": ("额外费用", "高于正常价格的价款", "全部服务费", "定金"),
        },
    ),
    QuestionTemplate(
        "电子商务",
        "brief",
        "我在{platform}购买商品后遇到{problem}，平台是否需要协助赔偿？",
        {
            "platform": ("网络购物平台", "直播间", "二手交易平台", "社交平台店铺"),
            "problem": ("商家失联", "收到假货", "付款后不发货", "退货后不退款"),
        },
    ),
    QuestionTemplate(
        "广告宣传",
        "brief",
        "{business}宣传{claim}，但实际{reality}，我能要求退款赔偿吗？",
        {
            "business": ("培训机构", "医美机构", "保健品商家", "房地产销售人员"),
            "claim": ("保证效果", "绝对安全", "全网最低价", "限时优惠"),
            "reality": ("完全没有达到宣传效果", "存在未告知风险", "价格并非最低", "优惠长期存在"),
        },
    ),
    QuestionTemplate(
        "药品安全",
        "brief",
        "我购买的{product}存在{problem}，使用后{result}，销售方应承担什么责任？",
        {
            "product": ("处方药", "非处方药", "网络销售药品", "进口药品"),
            "problem": ("超过有效期", "说明书信息不全", "来源不明", "包装破损"),
            "result": ("出现不良反应", "延误治疗", "产生额外医疗费", "尚未使用"),
        },
    ),
    QuestionTemplate(
        "价格纠纷",
        "brief",
        "{business}存在{behavior}，结账金额与预期不符，我可以要求退还差价吗？",
        {
            "business": ("餐馆", "酒店", "停车场", "网络平台", "零售商店"),
            "behavior": ("不明码标价", "低标高结", "临时加价", "收取未告知费用"),
        },
    ),
    QuestionTemplate(
        "侵权责任",
        "brief",
        "我在{place}因{cause}受伤，经营者是否需要赔偿医疗费和误工损失？",
        {
            "place": ("商场", "酒店", "健身房", "游乐场", "小区公共区域"),
            "cause": ("地面湿滑且没有警示", "设施损坏", "工作人员操作不当", "安全措施不足"),
        },
    ),
)

DETAILED_TEMPLATES = (
    QuestionTemplate(
        "劳动争议",
        "detailed",
        "{time}，{worker}入职一家{company}担任{job}，双方口头约定月工资{salary}元，"
        "但公司一直{contract_issue}。从{arrears_start}开始，公司已经拖欠{duration}工资，"
        "负责人多次以资金紧张为由推迟支付。{worker}保存了考勤记录、工作聊天、工资转账记录和催款截图，"
        "现在希望解除劳动关系，并了解能否要求补发工资、未签书面劳动合同的二倍工资以及经济补偿。",
        {
            "time": ("2025年3月", "2025年7月", "2026年1月"),
            "worker": ("张女士", "李先生", "王先生"),
            "company": ("互联网公司", "餐饮企业", "培训机构", "物流公司"),
            "job": ("运营", "服务员", "课程顾问", "仓库管理员"),
            "salary": ("6500", "8000", "10000"),
            "contract_issue": ("没有签订书面劳动合同", "拒绝向员工提供劳动合同", "没有缴纳社会保险"),
            "arrears_start": ("2025年11月", "2026年1月", "2026年3月"),
            "duration": ("两个月", "三个月", "四个月"),
        },
    ),
    QuestionTemplate(
        "合同纠纷",
        "detailed",
        "{time}，{buyer}与一家{seller}签订{contract}，约定总价{amount}元，"
        "并约定{deadline}完成交付。{buyer}已经支付{payment}，但对方{breach}，"
        "在多次微信催告后仍未解决。现有证据包括合同、付款凭证、聊天记录和催告记录。"
        "{buyer}想知道能否解除合同、要求返还已付款项，并主张违约金和实际损失。",
        {
            "time": ("2025年8月", "2025年12月", "2026年2月"),
            "buyer": ("陈先生", "某小型公司", "刘女士"),
            "seller": ("装修公司", "设备供应商", "培训机构", "软件服务商"),
            "contract": ("装修合同", "设备采购合同", "培训服务合同", "软件开发合同"),
            "amount": ("38000", "80000", "120000"),
            "deadline": ("30日内", "2026年3月底前", "收到预付款后45日内"),
            "payment": ("全部价款", "50%的预付款", "首期款"),
            "breach": ("超过约定期限仍未交付", "只完成少量工作后停止履行", "交付成果与合同约定严重不符"),
        },
    ),
    QuestionTemplate(
        "食品安全",
        "detailed",
        "{time}晚上，{consumer}通过{channel}在一家{merchant}购买{food}，支付{amount}元。"
        "食用后约{interval}，{consumer}出现{symptom}并前往医院，诊断为急性胃肠炎，"
        "已经产生医疗费和误工损失。{consumer}保留了订单、小票、食品照片、剩余食品、病历和付款记录，"
        "但商家只愿意退还餐费，不认可食品与身体不适之间存在关系。"
        "{consumer}想了解商家是否应承担赔偿责任、还需要补充哪些证据，以及可以主张哪些费用。",
        {
            "time": ("2026年4月12日", "2026年5月3日", "2026年6月18日"),
            "consumer": ("王女士", "赵先生", "李女士"),
            "channel": ("外卖平台", "线下门店", "网络团购平台"),
            "merchant": ("餐馆", "熟食店", "饮品店"),
            "food": ("海鲜套餐", "凉菜和熟食", "蛋糕和饮品"),
            "amount": ("128", "236", "358"),
            "interval": ("两小时", "四小时", "当天夜间"),
            "symptom": ("持续呕吐、腹泻和发热", "腹痛、恶心和脱水", "严重腹泻并伴随低烧"),
        },
    ),
    QuestionTemplate(
        "消费者权益",
        "detailed",
        "{time}，{consumer}在{channel}购买一台价值{amount}元的{goods}。"
        "销售人员承诺{promise}，但使用{period}后出现{problem}。"
        "{consumer}已经联系商家{attempts}，商家仍以人为损坏或超过退换期为由拒绝处理。"
        "目前保留了订单、发票、商品照片、维修检测记录和客服聊天。"
        "{consumer}希望了解能否要求退货退款、更换商品、承担检测费用或主张欺诈赔偿。",
        {
            "time": ("2025年双十一期间", "2026年1月", "2026年5月"),
            "consumer": ("周女士", "孙先生", "吴女士"),
            "channel": ("网络旗舰店", "商场专柜", "直播间"),
            "amount": ("3999", "6599", "8999"),
            "goods": ("手机", "笔记本电脑", "家用电器"),
            "promise": ("七天无理由退货且全国联保", "商品全新正品并提供一年保修", "出现质量问题可以免费换新"),
            "period": ("三天", "两周", "一个月"),
            "problem": ("无法开机并反复重启", "核心功能与宣传不符", "多次维修后仍存在相同故障"),
            "attempts": ("三次", "一个多月", "通过平台和门店多次"),
        },
    ),
    QuestionTemplate(
        "电子商务",
        "detailed",
        "{time}，{buyer}通过{platform}向一家店铺购买{goods}，支付{amount}元。"
        "页面标注{promise}，但收货后发现{problem}。{buyer}在平台申请退货并上传了开箱视频、"
        "商品照片和聊天记录，商家随后失联或拒绝退款，平台客服只回复正在协调。"
        "{buyer}想了解店铺和平台各自可能承担什么责任，如何要求退款赔偿，以及应当向哪个部门投诉。",
        {
            "time": ("2026年2月", "2026年4月", "2026年6月"),
            "buyer": ("高先生", "林女士", "某个体经营者"),
            "platform": ("网络购物平台", "直播电商平台", "二手交易平台"),
            "goods": ("品牌手表", "摄影设备", "办公电脑"),
            "amount": ("4800", "7600", "12500"),
            "promise": ("正品保障并支持七天无理由退货", "全新未拆封且假一赔十", "验货后不满意可以退款"),
            "problem": ("商品疑似假货", "型号和描述不符", "设备存在明显拆修痕迹"),
        },
    ),
    QuestionTemplate(
        "广告宣传",
        "detailed",
        "{time}，{consumer}看到一家{business}宣传{claim}，于是支付{amount}元购买相关服务。"
        "签约后才发现{reality}，合同中的限制条款在付款前也没有被特别说明。"
        "{consumer}保存了宣传页面截图、销售聊天、付款记录和合同，但机构拒绝退款并称广告只是效果展示。"
        "{consumer}想了解该宣传是否可能构成虚假或引人误解的商业宣传，以及能否解除合同并要求赔偿。",
        {
            "time": ("2025年9月", "2026年2月", "2026年5月"),
            "consumer": ("何女士", "郑先生", "冯女士"),
            "business": ("培训机构", "医美机构", "健身机构"),
            "claim": ("保证通过考试且不过全退", "一次治疗即可达到永久效果", "办理后可以在所有门店终身使用"),
            "amount": ("12800", "26000", "6800"),
            "reality": (
                "服务内容与宣传明显不一致",
                "实际效果和风险均未如实说明",
                "多家门店已经关闭且服务无法继续",
            ),
        },
    ),
    QuestionTemplate(
        "药品安全",
        "detailed",
        "{time}，{patient}通过{channel}购买{medicine}，支付{amount}元。"
        "服用后出现{reaction}，就医时发现该产品{problem}。"
        "{patient}保留了药品包装、购买订单、说明书、病历和检验报告，销售方则称个人体质不同，拒绝承担责任。"
        "{patient}想了解销售方和生产方的责任、医疗费用如何主张，以及是否应向药品监管部门报告。",
        {
            "time": ("2026年1月", "2026年3月", "2026年6月"),
            "patient": ("马女士", "唐先生", "许女士"),
            "channel": ("网络药店", "社区药房", "社交平台商家"),
            "medicine": ("处方药", "非处方药", "所谓进口药品"),
            "amount": ("380", "860", "1500"),
            "reaction": ("严重过敏反应", "持续头晕和呕吐", "病情加重并住院"),
            "problem": ("已经超过有效期", "来源和批准信息无法核实", "说明书没有标明相关禁忌"),
        },
    ),
    QuestionTemplate(
        "价格纠纷",
        "detailed",
        "{time}，{consumer}在{business}消费，现场标示价格为{shown_price}元，"
        "结账时却被收取{charged_price}元。经营者解释{reason}，但此前没有通过菜单、价目表或口头方式明确告知。"
        "{consumer}保留了付款记录、现场价格照片和沟通录音，希望了解是否属于不明码标价或价格欺诈，"
        "能否要求退还差价并向市场监管部门投诉。",
        {
            "time": ("2026年春节期间", "2026年5月1日", "2026年6月周末"),
            "consumer": ("蒋先生", "宋女士", "游客陈先生"),
            "business": ("餐馆", "酒店", "停车场", "景区商店"),
            "shown_price": ("198", "399", "60"),
            "charged_price": ("398", "699", "180"),
            "reason": ("节假日需要临时加价", "另有未标明的服务费", "标价只适用于部分时段"),
        },
    ),
    QuestionTemplate(
        "侵权责任",
        "detailed",
        "{time}，{victim}在{place}因{cause}摔倒受伤，随后被送往医院，诊断为{injury}。"
        "事故发生区域当时{security_issue}，现场监控可能记录了经过。{victim}已经保存医疗票据、"
        "现场照片、证人联系方式和与经营者沟通的记录，但经营者认为其本人没有注意安全，只愿承担少量费用。"
        "{victim}想了解经营者是否违反安全保障义务，以及医疗费、误工费和护理费应如何主张。",
        {
            "time": ("2026年2月", "2026年4月", "2026年6月"),
            "victim": ("钱女士", "邓先生", "郭女士"),
            "place": ("商场", "酒店", "健身房", "游乐场"),
            "cause": ("地面积水", "楼梯防滑条脱落", "健身器械突然损坏", "通道堆放杂物"),
            "injury": ("手腕骨折", "脚踝骨折", "腰部软组织损伤"),
            "security_issue": ("没有设置警示标志", "照明不足且没有工作人员提醒", "缺少必要的维护检查记录"),
        },
    ),
)

TEMPLATES = BRIEF_TEMPLATES + DETAILED_TEMPLATES
AVAILABLE_CATEGORIES = tuple(dict.fromkeys(template.category for template in TEMPLATES))
DETAIL_LEVELS = ("brief", "detailed")


def generate_question_examples(
    count: int,
    category: str | None = None,
    detail_level: Literal["brief", "detailed"] = "brief",
    *,
    rng: random.Random | None = None,
) -> list[dict[str, str]]:
    normalized_category = category.strip() if category else None
    if normalized_category and normalized_category not in AVAILABLE_CATEGORIES:
        options = "、".join(AVAILABLE_CATEGORIES)
        raise ValueError(f"不支持的案件分类：{normalized_category}；可选值：{options}")
    if detail_level not in DETAIL_LEVELS:
        raise ValueError("detail_level 只能是 brief 或 detailed")

    candidates = [
        template
        for template in TEMPLATES
        if template.detail_level == detail_level
        and (normalized_category is None or template.category == normalized_category)
    ]
    generator = rng or random.SystemRandom()
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    max_attempts = max(50, count * 20)
    for _ in range(max_attempts):
        template = generator.choice(candidates)
        question = template.render(generator)
        if question in seen:
            continue
        seen.add(question)
        example_id = hashlib.sha256(f"{template.category}:{question}".encode()).hexdigest()[:12]
        output.append(
            {
                "example_id": example_id,
                "category": template.category,
                "detail_level": template.detail_level,
                "question": question,
            }
        )
        if len(output) == count:
            return output
    raise RuntimeError("无法生成足够的不重复案件示例")
