"""Post-run deterministic statistics that do not alter the frozen evaluator."""

from __future__ import annotations

import math
from typing import Any, Iterable


def paired_comparison(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare frozen Raw and 10x10 predictions with an exact McNemar test."""

    by_sample: dict[str, dict[str, bool]] = {}
    for record in records:
        by_sample.setdefault(record["sample_id"], {})[record["config"]] = bool(record["correct"])
    expected = {"raw__vision_only", "grid_10x10__vision_only"}
    if any(set(pair) != expected for pair in by_sample.values()):
        raise ValueError("paired comparison requires one terminal record per frozen config")

    both_success = raw_only = grid_only = both_failed = 0
    for pair in by_sample.values():
        raw = pair["raw__vision_only"]
        grid = pair["grid_10x10__vision_only"]
        if raw and grid:
            both_success += 1
        elif raw:
            raw_only += 1
        elif grid:
            grid_only += 1
        else:
            both_failed += 1

    discordant = raw_only + grid_only
    if discordant:
        tail = sum(
            math.comb(discordant, index)
            for index in range(min(raw_only, grid_only) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    else:
        p_value = 1.0
    count = len(by_sample)
    return {
        "samples": count,
        "both_success": both_success,
        "raw_only_success": raw_only,
        "grid_10x10_only_success": grid_only,
        "both_failed": both_failed,
        "raw_accuracy": (both_success + raw_only) / count,
        "grid_10x10_accuracy": (both_success + grid_only) / count,
        "accuracy_difference_grid_minus_raw": (grid_only - raw_only) / count,
        "discordant_pairs": discordant,
        "exact_mcnemar_two_sided_p_value": p_value,
    }


def outside_bbox_metrics(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["config"], []).append(record)
    result = {}
    for config, rows in grouped.items():
        outside = sum(
            row["prediction_point"] is not None and not bool(row["correct"]) for row in rows
        )
        result[config] = {
            "outside_bbox_clicks": outside,
            "outside_bbox_click_rate": outside / len(rows),
        }
    return result
