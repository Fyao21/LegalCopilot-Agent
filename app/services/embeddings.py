import hashlib
import math
import re

from app.config import get_settings


def tokenize(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    if not normalized:
        return []
    if len(normalized) == 1:
        return [normalized]
    return [normalized[index:index + 2] for index in range(len(normalized) - 1)]


def embed(text: str) -> list[float]:
    """无需模型密钥的中文二元词哈希向量，仅用于第一周打通检索链路。"""
    dimensions = get_settings().embedding_dimensions
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        position = int.from_bytes(digest[:8], "big") % dimensions
        vector[position] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    return sum(a * b for a, b in zip(left, right))

