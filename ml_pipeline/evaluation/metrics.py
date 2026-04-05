"""
Evaluation Metrics for recommendation models.
Precision@K, Recall@K, NDCG@K, Hit Rate, Coverage.
"""
import logging
import math
from collections import defaultdict
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def precision_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """Precision@K: fraction of recommended items that are relevant."""
    rec_k = recommended[:k]
    if not rec_k:
        return 0.0
    hits = sum(1 for item in rec_k if item in relevant)
    return hits / k


def recall_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """Recall@K: fraction of relevant items that are recommended."""
    if not relevant:
        return 0.0
    rec_k = recommended[:k]
    hits = sum(1 for item in rec_k if item in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """NDCG@K: Normalized Discounted Cumulative Gain."""
    rec_k = recommended[:k]
    dcg = 0.0
    for i, item in enumerate(rec_k):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)  # position 1-indexed

    # Ideal DCG
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    return dcg / idcg if idcg > 0 else 0.0


def hit_rate_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """Hit Rate@K: 1 if any recommended item is relevant, 0 otherwise."""
    rec_k = recommended[:k]
    return 1.0 if any(item in relevant for item in rec_k) else 0.0


def coverage(all_recommendations: list[list[str]], total_items: int) -> float:
    """Coverage: fraction of all items that appear in any recommendation list."""
    recommended_items = set()
    for rec_list in all_recommendations:
        recommended_items.update(rec_list)
    return len(recommended_items) / total_items if total_items > 0 else 0.0


def evaluate_model(
    model_name: str,
    recommend_fn,
    test_data: pd.DataFrame,
    all_interactions: pd.DataFrame,
    k_values: list[int] = None,
    num_items: int = None,
) -> dict:
    """
    Evaluate a recommendation model on test data.
    
    Args:
        model_name: name of the model
        recommend_fn: function(user_id) -> list[(track_id, score)]
        test_data: test DataFrame with user_id, track_id, label columns
        all_interactions: all interactions for building seen sets
        k_values: list of K values for @K metrics
        num_items: total number of items (for coverage)
    
    Returns:
        dict with metrics
    """
    k_values = k_values or [5, 10, 20]

    # Build ground truth per user: items in test set that user liked
    user_test_positive = test_data[test_data["label"] == 1].groupby("user_id")["track_id"].apply(set).to_dict()

    if not user_test_positive:
        logger.warning(f"No positive test cases for {model_name}")
        return {}

    # Compute metrics
    metrics = {f"precision@{k}": [] for k in k_values}
    metrics.update({f"recall@{k}": [] for k in k_values})
    metrics.update({f"ndcg@{k}": [] for k in k_values})
    metrics.update({f"hr@{k}": [] for k in k_values})

    all_recs = []
    eval_users = 0

    for user_id, relevant in user_test_positive.items():
        if not relevant:
            continue

        try:
            recs = recommend_fn(user_id)
            rec_ids = [r[0] if isinstance(r, tuple) else r for r in recs]
        except Exception as e:
            continue

        if not rec_ids:
            continue

        all_recs.append(rec_ids)
        eval_users += 1

        for k in k_values:
            metrics[f"precision@{k}"].append(precision_at_k(rec_ids, relevant, k))
            metrics[f"recall@{k}"].append(recall_at_k(rec_ids, relevant, k))
            metrics[f"ndcg@{k}"].append(ndcg_at_k(rec_ids, relevant, k))
            metrics[f"hr@{k}"].append(hit_rate_at_k(rec_ids, relevant, k))

    # Average
    result = {"model": model_name, "eval_users": eval_users}
    for metric_name, values in metrics.items():
        result[metric_name] = np.mean(values) if values else 0.0

    # Coverage
    if num_items:
        result["coverage"] = coverage(all_recs, num_items)

    return result


def format_report(results: list[dict], k_values: list[int] = None) -> str:
    """Format evaluation results as a markdown table."""
    k_values = k_values or [5, 10, 20]

    header_cols = ["Model", "Users"]
    for k in k_values:
        header_cols.extend([f"P@{k}", f"R@{k}", f"NDCG@{k}", f"HR@{k}"])
    header_cols.append("Coverage")

    lines = []
    lines.append("# 推荐模型评测对比报告\n")
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

    for r in results:
        row = [r.get("model", "?"), str(r.get("eval_users", 0))]
        for k in k_values:
            row.extend([
                f"{r.get(f'precision@{k}', 0):.4f}",
                f"{r.get(f'recall@{k}', 0):.4f}",
                f"{r.get(f'ndcg@{k}', 0):.4f}",
                f"{r.get(f'hr@{k}', 0):.4f}",
            ])
        row.append(f"{r.get('coverage', 0):.4f}")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
