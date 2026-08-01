from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.schemas import LegalArticleCreate

MAX_BATCH_FILES = 200
MAX_BATCH_FILE_BYTES = 128 * 1024
MAX_BATCH_TOTAL_BYTES = 8 * 1024 * 1024


class KnowledgeImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedKnowledgeFile:
    filename: str
    article: LegalArticleCreate


def parse_knowledge_text_file(filename: str, data: bytes) -> ParsedKnowledgeFile:
    safe_name = Path(filename or "未命名.txt").name
    if Path(safe_name).suffix.lower() != ".txt":
        raise KnowledgeImportError("仅支持 .txt 文件")
    if not data:
        raise KnowledgeImportError("文件为空")
    if len(data) > MAX_BATCH_FILE_BYTES:
        raise KnowledgeImportError("单个文件不能超过 128 KB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise KnowledgeImportError("文件必须使用 UTF-8 编码") from error

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 4:
        raise KnowledgeImportError("文件至少需要四行：名称、条号、来源、正文")

    try:
        article = LegalArticleCreate(
            law_name=lines[0],
            article_number=lines[1],
            source=lines[2],
            content="\n".join(lines[3:]),
        )
    except ValidationError as error:
        first_error = error.errors()[0]
        field = str(first_error.get("loc", ["字段"])[0])
        message = str(first_error.get("msg", "格式不正确"))
        raise KnowledgeImportError(f"{field}：{message}") from error
    return ParsedKnowledgeFile(filename=safe_name, article=article)
