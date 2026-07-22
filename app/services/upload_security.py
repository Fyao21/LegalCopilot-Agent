from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import UploadFile

from app.services.document_parser import UnsupportedDocumentError, extract_text


ALLOWED_CONTENT_TYPES = {
    ".txt": {"text/plain", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".pdf": {"application/pdf", "application/octet-stream"},
}


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 415):
        super().__init__(message)
        self.status_code = status_code


def safe_display_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    basename = filename.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]", "_", basename).strip("._")
    return cleaned[:180] or "uploaded-file"


async def read_and_extract_upload(
    upload: UploadFile | None,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> tuple[str | None, str]:
    if upload is None or not upload.filename:
        return None, ""

    filename = safe_display_filename(upload.filename)
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_CONTENT_TYPES:
        raise UploadValidationError("仅支持 .txt、.docx、.pdf 文件")

    content_type = (upload.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_CONTENT_TYPES[suffix]:
        raise UploadValidationError("文件扩展名与 MIME 类型不匹配")

    try:
        content = await upload.read(max_bytes + 1)
    finally:
        await upload.close()
    if len(content) > max_bytes:
        limit_mb = max_bytes / 1024 / 1024
        raise UploadValidationError(f"文件不能超过 {limit_mb:g} MB", status_code=413)
    if not content:
        raise UploadValidationError("上传文件为空", status_code=422)

    try:
        extracted = await asyncio.wait_for(
            asyncio.to_thread(extract_text, filename or "", content),
            timeout=timeout_seconds,
        )
    except TimeoutError as error:
        raise UploadValidationError("文件解析超时", status_code=408) from error
    except UnsupportedDocumentError as error:
        raise UploadValidationError(str(error)) from error
    except Exception as error:
        raise UploadValidationError("文件损坏或无法解析", status_code=422) from error
    return filename, extracted
