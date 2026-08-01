import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.llm import OpenAICompatibleLLM
from app.services.knowledge_import import MAX_BATCH_FILE_BYTES, KnowledgeImportError

MAX_NORMALIZATION_CHARACTERS = 30000


class KnowledgeNormalizationDraft(BaseModel):
    law_name: str | None = None
    article_number: str | None = None
    source: str | None = None
    content: str | None = Field(default=None, min_length=2, max_length=20000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    multiple_articles_detected: bool = False

    @field_validator("law_name", "article_number", "source", "content", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return value


SYSTEM_PROMPT = """你是法规 TXT 格式整理 Agent。输入是一份排版不固定、但理论上只描述一条法规条文的 TXT。
请只提取原文已经明确提供的信息，不得编造法律名称、条号、来源或正文。
返回 JSON 字段：law_name、article_number、source、content、confidence、warnings、multiple_articles_detected。

要求：
1. law_name 使用原文中的法规正式名称；没有明确名称时返回 null。
2. article_number 使用“第……条”形式；原文未提供时返回 null，不能猜测。
3. source 保留原文中的来源名称、网址或出处；未提供时返回 null。
4. content 只整理该条法规正文，去除字段标签、页眉、页脚和无关说明，但不得概括、改写或补写正文。
5. 如果检测到多条不同条号，multiple_articles_detected=true，并在 warnings 说明本接口只整理第一条，必须人工拆分核对。
6. warnings 必须是 JSON 字符串数组；confidence 为 0 到 1。
7. 不要输出 Markdown，不要解释，只返回 JSON。"""


def decode_unstructured_knowledge_file(filename: str, data: bytes) -> tuple[str, str]:
    safe_name = Path(filename or "未命名.txt").name
    if Path(safe_name).suffix.lower() != ".txt":
        raise KnowledgeImportError("智能整理仅支持 .txt 文件")
    if not data:
        raise KnowledgeImportError("文件为空")
    if len(data) > MAX_BATCH_FILE_BYTES:
        raise KnowledgeImportError("单个文件不能超过 128 KB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise KnowledgeImportError("文件必须使用 UTF-8 编码") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) < 2:
        raise KnowledgeImportError("文件中没有可整理的文本")
    if len(normalized) > MAX_NORMALIZATION_CHARACTERS:
        raise KnowledgeImportError(f"文本不能超过 {MAX_NORMALIZATION_CHARACTERS} 个字符")
    return safe_name, normalized


def normalize_knowledge_text(
    filename: str,
    text: str,
    llm: OpenAICompatibleLLM,
) -> dict[str, object]:
    payload = json.dumps({"filename": filename, "raw_text": text}, ensure_ascii=False)
    draft = llm.invoke_structured(SYSTEM_PROMPT, payload, KnowledgeNormalizationDraft)
    missing_fields = [
        field
        for field, value in (
            ("law_name", draft.law_name),
            ("article_number", draft.article_number),
            ("source", draft.source),
            ("content", draft.content),
        )
        if not value
    ]
    warnings = list(draft.warnings)
    unverified_fields: list[str] = []
    labels = {
        "law_name": "法律名称",
        "article_number": "条号",
        "source": "来源",
    }
    for field, label in labels.items():
        value = getattr(draft, field)
        if value and value not in text:
            warnings.append(f"模型提取的{label}无法在原文中逐字定位，请人工核对")
            unverified_fields.append(field)
    normalized_raw = re.sub(r"\s+", "", text)
    normalized_content = re.sub(r"\s+", "", draft.content or "")
    if normalized_content and normalized_content not in normalized_raw:
        warnings.append("模型整理后的正文无法在原文中连续定位，请逐字核对，确认模型没有改写或补写")
        unverified_fields.append("content")
    if draft.multiple_articles_detected:
        warnings.append("检测到多个条号；标准文件只保留模型识别的第一条，请拆分原文件后分别整理")
    if missing_fields:
        warnings.append(f"以下字段缺失，下载或入库前必须补充：{', '.join(missing_fields)}")
    warnings = list(dict.fromkeys(warnings))

    placeholders = {
        "law_name": "[待补充法律名称]",
        "article_number": "[待补充条号]",
        "source": "[待补充来源]",
        "content": "[待补充正文]",
    }
    standard_values = {
        "law_name": draft.law_name or placeholders["law_name"],
        "article_number": draft.article_number or placeholders["article_number"],
        "source": draft.source or placeholders["source"],
        "content": draft.content or placeholders["content"],
    }
    standardized_text = "\n".join(
        standard_values[field] for field in ("law_name", "article_number", "source", "content")
    )
    safe_stem = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", Path(filename).stem).strip("_")
    return {
        "original_filename": filename,
        "standardized_filename": f"{safe_stem or 'normalized'}_standardized.txt",
        "law_name": draft.law_name,
        "article_number": draft.article_number,
        "source": draft.source,
        "content": draft.content or "",
        "confidence": draft.confidence,
        "missing_fields": missing_fields,
        "warnings": warnings,
        "multiple_articles_detected": draft.multiple_articles_detected,
        "ready_for_import": (
            not missing_fields and not draft.multiple_articles_detected and not unverified_fields
        ),
        "requires_human_review": True,
        "standardized_text": standardized_text,
        "model": llm.model,
    }
