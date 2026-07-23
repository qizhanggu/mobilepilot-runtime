"""ScreenSpot-v2 的确定性 point-in-bbox 等价 Evaluator。"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def normalized_to_pixel(point: list[int], image_size: tuple[int, int]) -> tuple[int, int]:
    if len(point) != 2:
        raise ValueError("normalized point must contain x and y")
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    x = min(width - 1, max(0, int(point[0] / 1000 * width)))
    y = min(height - 1, max(0, int(point[1] / 1000 * height)))
    return (x, y)


def point_in_bbox_xywh(point: tuple[int, int], bbox_xywh: tuple[int, int, int, int]) -> bool:
    """按论文规则判断预测点是否落入目标框，边界计为命中。"""

    x, y, width, height = bbox_xywh
    px, py = point
    return x <= px <= x + width and y <= py <= y + height


def summarize_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["config"], []).append(record)

    summaries = []
    for config, rows in sorted(grouped.items()):
        valid = [row for row in rows if row["prediction_point"] is not None]
        costs = [row["estimated_list_cost_cny"] for row in rows if row.get("estimated_list_cost_cny") is not None]
        summary: dict[str, Any] = {
            "config": config,
            "samples": len(rows),
            "correct": sum(bool(row["correct"]) for row in rows),
            "accuracy": sum(bool(row["correct"]) for row in rows) / len(rows),
            "invalid_outputs": len(rows) - len(valid),
            "invalid_output_rate": (len(rows) - len(valid)) / len(rows),
            "model_call_count": sum(int(row["model_call_count"]) for row in rows),
            "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
            "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
            "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
            "estimated_list_cost_cny": sum(costs) if costs else None,
            "mean_latency_seconds": sum(float(row["latency_seconds"]) for row in rows) / len(rows),
            "failure_reasons": dict(Counter(row["failure_reason"] or "success" for row in rows)),
        }
        for data_type in ("text", "icon"):
            typed = [row for row in rows if row["data_type"] == data_type]
            summary[f"{data_type}_samples"] = len(typed)
            summary[f"{data_type}_accuracy"] = (
                sum(bool(row["correct"]) for row in typed) / len(typed) if typed else None
            )
        summaries.append(summary)
    return summaries
