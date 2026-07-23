"""ScreenSpot 逐样本记录的汇总和可视化导出。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw

from .evaluator import summarize_records


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_summary(records: Iterable[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    records = list(records)
    summary = summarize_records(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if summary:
        fields = [key for key in summary[0] if key != "failure_reasons"]
        with (output_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: row[key] for key in fields} for row in summary)
    return summary


def render_audit_examples(
    records: Iterable[dict[str, Any]],
    *,
    output_dir: Path,
    limit_per_config: int = 4,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[tuple[str, bool], int] = {}
    for record in records:
        key = (record["config"], bool(record["correct"]))
        if counts.get(key, 0) >= limit_per_config:
            continue
        image_path = Path(record["image_path"])
        if not image_path.exists():
            continue
        image = Image.open(image_path).convert("RGB")
        from .preprocess import ImageVariant, apply_image_variant

        image = apply_image_variant(image, ImageVariant(record["image_variant"]))
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = record["target_bbox_xyxy"]
        draw.rectangle((left, top, right, bottom), outline=(0, 200, 0), width=max(3, image.width // 300))
        if record["prediction_point"] is not None:
            x, y = record["prediction_point"]
            radius = max(6, image.width // 150)
            color = (0, 180, 0) if record["correct"] else (240, 40, 40)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=max(3, radius // 3))
        suffix = "success" if record["correct"] else "failure"
        image.save(output_dir / f"{record['config']}__{suffix}__{record['sample_id']}.png")
        counts[key] = counts.get(key, 0) + 1
