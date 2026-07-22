from dataclasses import dataclass


@dataclass(frozen=True)
class LegalTextChunk:
    article_number: str
    chunk_index: int
    content: str


def split_legal_article(
    article_number: str,
    content: str,
    max_chars: int = 800,
    overlap_chars: int = 80,
) -> list[LegalTextChunk]:
    """按段落切分超长法条，同时保留原始条号和稳定序号。"""
    normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    if not normalized:
        return []
    if max_chars < 100:
        raise ValueError("max_chars 不能小于 100")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars 必须大于等于 0 且小于 max_chars")
    if len(normalized) <= max_chars:
        return [LegalTextChunk(article_number, 0, normalized)]

    chunks: list[LegalTextChunk] = []
    start = 0
    index = 0
    while start < len(normalized):
        hard_end = min(len(normalized), start + max_chars)
        end = hard_end
        if hard_end < len(normalized):
            candidates = [normalized.rfind(mark, start + max_chars // 2, hard_end) for mark in ("\n", "。", "；")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        chunks.append(LegalTextChunk(article_number, index, normalized[start:end].strip()))
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap_chars)
        index += 1
    return chunks
