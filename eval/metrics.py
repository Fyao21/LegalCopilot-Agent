from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    case_text: str
    question: str
    expected_case_type: str
    key_fact_keywords: list[str]
    dispute_focus_keywords: list[str]
    relevant_article_ids: list[int]
    source_note: str
    ambiguity_note: str = ""


def load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            case = EvalCase(**row)
            if case.case_id in seen_ids:
                raise ValueError(f"评测集第 {line_number} 行存在重复 case_id：{case.case_id}")
            if not case.relevant_article_ids:
                raise ValueError(f"评测样例 {case.case_id} 缺少相关 article_id")
            seen_ids.add(case.case_id)
            cases.append(case)
    if not cases:
        raise ValueError("评测集不能为空")
    return cases


def keyword_coverage(expected: list[str], predicted_text: str) -> float:
    if not expected:
        return 1.0
    normalized = "".join(predicted_text.lower().split())
    matched = sum("".join(keyword.lower().split()) in normalized for keyword in expected)
    return matched / len(expected)


def reciprocal_rank(ranked_ids: list[int], relevant_ids: list[int]) -> float:
    relevant = set(relevant_ids)
    for rank, article_id in enumerate(ranked_ids, 1):
        if article_id in relevant:
            return 1.0 / rank
    return 0.0


def recall_at_k(ranked_ids: list[int], relevant_ids: list[int], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return len(relevant & set(ranked_ids[:k])) / len(relevant)


def precision_at_k(ranked_ids: list[int], relevant_ids: list[int], k: int) -> float:
    selected = ranked_ids[:k]
    if not selected:
        return 0.0
    return len(set(selected) & set(relevant_ids)) / len(selected)


def hit_at_k(ranked_ids: list[int], relevant_ids: list[int], k: int) -> float:
    return float(bool(set(ranked_ids[:k]) & set(relevant_ids)))


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[position]


def aggregate_retrieval(rows: list[dict[str, object]]) -> dict[str, float]:
    def values(key: str) -> list[float]:
        output: list[float] = []
        for row in rows:
            value = row[key]
            if not isinstance(value, (int, float)):
                raise TypeError(f"指标 {key} 必须是数值")
            output.append(float(value))
        return output

    latencies = values("latency_ms")
    return {
        "recall_at_5": round(mean(values("recall_at_5")), 4),
        "mrr": round(mean(values("mrr")), 4),
        "hit_at_1": round(mean(values("hit_at_1")), 4),
        "hit_at_3": round(mean(values("hit_at_3")), 4),
        "hit_at_5": round(mean(values("hit_at_5")), 4),
        "precision_at_5": round(mean(values("precision_at_5")), 4),
        "average_latency_ms": round(mean(latencies), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
    }
