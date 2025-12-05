import math
import re
import statistics
from typing import Iterable, Optional, Sequence

ARTICLES = {"a", "an", "the"}
REFUSAL_RE = re.compile(
    r"(i (do not|don't) know|cannot (find|answer)|no answer|no information|not sure|can't find)",
    re.IGNORECASE,
)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in ARTICLES]
    return " ".join(tokens)


def em_f1(pred: str, gold: Optional[str], aliases: Optional[Iterable[str]] = None) -> tuple[float, float]:
    """
    Exact Match and token-level F1 for answerable questions.
    If gold is None/empty, returns (0.0, 0.0).
    """
    if not gold:
        return 0.0, 0.0
    golds = [gold] + list(aliases or [])
    norm_pred = _normalize(pred)
    em = 0.0
    best_f1 = 0.0
    for g in golds:
        norm_gold = _normalize(g)
        if not norm_gold and not norm_pred:
            return 1.0, 1.0
        if norm_pred == norm_gold:
            em = 1.0
        pred_tokens = norm_pred.split()
        gold_tokens = norm_gold.split()
        if not gold_tokens or not pred_tokens:
            f1 = 1.0 if norm_pred == norm_gold else 0.0
        else:
            common = set(pred_tokens) & set(gold_tokens)
            tp = sum(min(pred_tokens.count(t), gold_tokens.count(t)) for t in common)
            if tp == 0:
                f1 = 0.0
            else:
                precision = tp / len(pred_tokens)
                recall = tp / len(gold_tokens)
                f1 = 2 * precision * recall / (precision + recall)
        best_f1 = max(best_f1, f1)
    return em, best_f1


def is_refusal(text: str) -> bool:
    return bool(REFUSAL_RE.search(text or ""))


def refusal_ok(pred: str, unanswerable: bool) -> Optional[int]:
    if not unanswerable:
        return None
    return 1 if is_refusal(pred) else 0


def extract_gold_doc_ids(rec: dict) -> list[str]:
    if rec.get("gold_docs"):
        return list(rec["gold_docs"])
    supp = rec.get("supporting_docs") or []
    return [d["doc_id"] for d in supp if isinstance(d, dict) and d.get("doc_id")]


def citation_hit(citations: Iterable[dict], gold_doc_ids: Sequence[str]) -> Optional[int]:
    """
    None if no gold_doc_ids; 1 if any citation matches; else 0.
    Match uses case-insensitive equality against doc_id/sourceId/uri/filename.
    """
    if not gold_doc_ids:
        return None
    gold_norm = [str(g).lower() for g in gold_doc_ids]
    for c in citations or []:
        candidate = (
            c.get("doc_id")
            or c.get("sourceId")
            or c.get("uri")
            or c.get("title")
            or ""
        )
        candidate = str(candidate).lower()
        if candidate and any(candidate == g for g in gold_norm):
            return 1
    return 0


def mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = (len(vals) - 1) * 0.95
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] + (vals[c] - vals[f]) * (k - f)
