"""视觉主链路的受控真机对照实验。

该模块只服务实验：初始化 MobilePilot Lab、构造截图变体、调用 GUI-Plus、
执行安全的本地点击并落盘指标。vision_only 在目标选择和验证阶段均不请求 UI Tree；
vision_with_tree_aux 只在视觉候选产生后读取 UI Tree 做辅助检查。
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from enum import Enum
import json
import os
from pathlib import Path
import random
import statistics
import time
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageStat

from mobile_pilot.device import Uiautomator2DeviceAdapter
from mobile_pilot.perception import ScreenState
from mobile_pilot.policy import Grounder, GroundingCandidate, GroundingSource, GuiPlusRequest, GuiPlusVisionPolicy, SemanticTarget


PACKAGE = "com.mobilepilot.lab"
DEFAULT_SERIAL = os.getenv("ANDROID_SERIAL", "")
DEFAULT_OUTPUT = Path("artifacts/evaluation/visual-mainline-20260722")


class VisualVariant(str, Enum):
    RAW = "raw"
    GRID_10X10 = "grid_10x10"
    COARSE_TO_FINE = "coarse_to_fine"


class EvaluationMode(str, Enum):
    VISION_ONLY = "vision_only"
    VISION_WITH_TREE_AUX = "vision_with_tree_aux"
    TREE_FIRST = "tree_first"


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    mode: EvaluationMode
    visual_variant: VisualVariant


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    instruction: str
    setup: str
    target_bounds: tuple[int, int, int, int]
    target_resource_id: str = ""


EXPERIMENT_CONFIGS = (
    ExperimentConfig("raw__vision_only", EvaluationMode.VISION_ONLY, VisualVariant.RAW),
    ExperimentConfig("grid10__vision_only", EvaluationMode.VISION_ONLY, VisualVariant.GRID_10X10),
    ExperimentConfig("coarse_fine__vision_only", EvaluationMode.VISION_ONLY, VisualVariant.COARSE_TO_FINE),
    ExperimentConfig("raw__tree_aux", EvaluationMode.VISION_WITH_TREE_AUX, VisualVariant.RAW),
    ExperimentConfig("grid10__tree_aux", EvaluationMode.VISION_WITH_TREE_AUX, VisualVariant.GRID_10X10),
    ExperimentConfig("coarse_fine__tree_aux", EvaluationMode.VISION_WITH_TREE_AUX, VisualVariant.COARSE_TO_FINE),
    ExperimentConfig("tree_first", EvaluationMode.TREE_FIRST, VisualVariant.RAW),
)


TASKS = (
    TaskSpec(
        "home_search_input",
        "点击搜索关键词输入框，不要点击搜索按钮。",
        "home",
        (70, 669, 1190, 847),
        f"{PACKAGE}:id/search_input",
    ),
    TaskSpec(
        "home_search_button",
        "点击文字为“搜索”的按钮，不要点击输入框。",
        "home_prefilled",
        (70, 847, 1190, 1015),
        f"{PACKAGE}:id/search_button",
    ),
    TaskSpec(
        "home_debug_dialog",
        "点击“显示测试弹窗”按钮。",
        "home",
        (70, 1015, 1190, 1183),
        f"{PACKAGE}:id/debug_dialog_button",
    ),
    TaskSpec(
        "home_visual_canvas",
        "点击蓝色的“视觉专用按钮：点我验证”，不要点击上方灰色按钮。",
        "home",
        (85, 1198, 1175, 1469),
    ),
    TaskSpec(
        "test_dialog_close",
        "关闭当前“测试弹窗”，点击右下角“关闭”。",
        "test_dialog",
        (906, 1628, 1130, 1817),
        "android:id/button1",
    ),
    TaskSpec(
        "visual_dialog_close",
        "关闭当前“视觉定位验证成功”弹窗，点击右下角“关闭”。",
        "visual_dialog",
        (906, 1578, 1130, 1767),
        "android:id/button1",
    ),
    TaskSpec(
        "results_filter",
        "点击“筛选评分 4.5 以上”按钮。",
        "results",
        (70, 587, 1190, 755),
        f"{PACKAGE}:id/filter_button",
    ),
    TaskSpec(
        "results_review",
        "点击“前往确认页”按钮，不要点击重置。",
        "results",
        (70, 1406, 1190, 1574),
        f"{PACKAGE}:id/review_order_button",
    ),
)


class VisualMatrixRunner:
    def __init__(self, serial: str, output_dir: Path):
        import uiautomator2 as u2

        self.serial = serial
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = u2.connect(serial)
        self.adapter = Uiautomator2DeviceAdapter(serial, client=self.device)
        self.policy = GuiPlusVisionPolicy()
        self.grounder = Grounder()
        self.records_path = output_dir / "runs.jsonl"

    def run(
        self,
        *,
        repeats: int = 3,
        tasks: Iterable[TaskSpec] = TASKS,
        configs: Iterable[ExperimentConfig] = EXPERIMENT_CONFIGS,
        seed: int = 20260722,
    ) -> list[dict[str, Any]]:
        tasks = tuple(tasks)
        configs = tuple(configs)
        completed = _completed_keys(self.records_path)
        schedule = [(repeat, task, config) for repeat in range(1, repeats + 1) for task in tasks for config in configs]
        random.Random(seed).shuffle(schedule)

        for repeat, task, config in schedule:
            key = (task.task_id, config.name, repeat)
            if key in completed:
                continue
            record = self.run_one(task, config, repeat)
            _append_jsonl(self.records_path, record)
            print(json.dumps({k: record[k] for k in ("task_id", "config", "repeat", "task_success", "failure_reason")}, ensure_ascii=False), flush=True)

        records = _read_jsonl(self.records_path)
        _write_summaries(records, self.output_dir)
        self._setup("home")
        return records

    def run_one(self, task: TaskSpec, config: ExperimentConfig, repeat: int) -> dict[str, Any]:
        self._setup(task.setup)
        run_started = time.perf_counter()
        model_calls: list[dict[str, Any]] = []
        candidate: GroundingCandidate | None = None
        blocked = False
        failure_reason = ""
        ui_tree_requests = 0

        # vision_only 和 tree_aux 的视觉决策都从纯截图开始；Tree 辅助只能发生在候选之后。
        if config.mode is EvaluationMode.TREE_FIRST:
            observation = self.adapter.observe(include_ui_tree=True)
            ui_tree_requests += 1
            state = ScreenState.from_observation(observation)
            before_image = observation.image
            try:
                candidate = self.grounder.resolve(SemanticTarget(resource_id=task.target_resource_id), state)
            except LookupError:
                candidate, calls, failure_reason = self._visual_candidate(task, config.visual_variant, before_image)
                model_calls.extend(calls)
                if candidate is not None:
                    blocked, aux_reason = _tree_auxiliary_check(candidate.point, task, state)
                    failure_reason = aux_reason if blocked else failure_reason
        else:
            observation = self.adapter.observe(include_ui_tree=False)
            state = ScreenState.from_observation(observation)
            before_image = observation.image
            candidate, calls, failure_reason = self._visual_candidate(task, config.visual_variant, before_image)
            model_calls.extend(calls)
            if candidate is not None and config.mode is EvaluationMode.VISION_WITH_TREE_AUX:
                aux_observation = self.adapter.observe(include_ui_tree=True)
                ui_tree_requests += 1
                aux_state = ScreenState.from_observation(aux_observation)
                blocked, aux_reason = _tree_auxiliary_check(candidate.point, task, aux_state)
                if blocked:
                    failure_reason = aux_reason

        correct_point = candidate is not None and _contains(task.target_bounds, candidate.point)
        executed = False
        screen_changed = False
        image_change_score = 0.0
        wrong_click = False
        if candidate is not None and not blocked:
            self.adapter.tap_point(*candidate.point)
            executed = True
            wrong_click = not correct_point
            time.sleep(0.35)
            verify_tree = config.mode is not EvaluationMode.VISION_ONLY
            after = self.adapter.observe(include_ui_tree=verify_tree)
            ui_tree_requests += int(verify_tree)
            image_change_score = _image_change_score(before_image, after.image)
            screen_changed = image_change_score >= 0.05

        task_success = bool(correct_point and executed and screen_changed)
        if not failure_reason and not task_success:
            if candidate is None:
                failure_reason = "model_or_parser_failure"
            elif blocked:
                failure_reason = "tree_aux_blocked"
            elif not correct_point:
                failure_reason = "candidate_outside_target"
            elif not screen_changed:
                failure_reason = "post_action_screen_unchanged"

        return {
            "task_id": task.task_id,
            "instruction": task.instruction,
            "config": config.name,
            "mode": config.mode.value,
            "visual_variant": config.visual_variant.value,
            "repeat": repeat,
            "target_bounds": list(task.target_bounds),
            "candidate_point": list(candidate.point) if candidate else None,
            "candidate_source": candidate.source.value if candidate else None,
            "candidate_correct": bool(correct_point),
            "critic_blocked": blocked,
            "executed": executed,
            "wrong_click": wrong_click,
            "screen_changed": screen_changed,
            "image_change_score": image_change_score,
            "step_success": task_success,
            "task_success": task_success,
            "model_call_count": len(model_calls),
            "model_calls": model_calls,
            "prompt_tokens": _sum_present(model_calls, "prompt_tokens"),
            "completion_tokens": _sum_present(model_calls, "completion_tokens"),
            "total_tokens": _sum_present(model_calls, "total_tokens"),
            "estimated_list_cost_cny": _sum_present(model_calls, "estimated_list_cost_cny"),
            "model_latency_seconds": sum(float(call["latency_seconds"]) for call in model_calls),
            "run_latency_seconds": time.perf_counter() - run_started,
            "ui_tree_requests_after_setup": ui_tree_requests,
            "failure_reason": failure_reason,
        }

    def _visual_candidate(
        self,
        task: TaskSpec,
        variant: VisualVariant,
        image: Image.Image,
    ) -> tuple[GroundingCandidate | None, list[dict[str, Any]], str]:
        if variant is VisualVariant.RAW:
            return self._single_visual_call(task.instruction, image)
        if variant is VisualVariant.GRID_10X10:
            instruction = task.instruction + " 截图包含10×10等分网格，坐标仍使用整张图的0到1000归一化坐标。"
            return self._single_visual_call(instruction, add_grid(image, 10, 10))

        coarse, calls, reason = self._single_visual_call(
            "先在整张手机截图上粗略定位目标中心：" + task.instruction,
            image,
        )
        if coarse is None:
            return None, calls, reason
        viewport = crop_around(image.size, coarse.point)
        crop = image.crop(viewport)
        fine, fine_calls, fine_reason = self._single_visual_call(
            "这是从原始手机截图裁剪出的局部区域。请精确点击目标：" + task.instruction,
            crop,
        )
        calls.extend(fine_calls)
        if fine is None:
            return None, calls, fine_reason
        left, top, _, _ = viewport
        point = (left + fine.point[0], top + fine.point[1])
        return GroundingCandidate(point, GroundingSource.VISION, 0.55, "Coarse-to-fine visual candidate."), calls, ""

    def _single_visual_call(
        self,
        instruction: str,
        image: Image.Image,
    ) -> tuple[GroundingCandidate | None, list[dict[str, Any]], str]:
        decision = self.policy.decide_with_metrics(GuiPlusRequest(instruction, image))
        call = asdict(decision.metrics)
        call["parse_success"] = decision.result.is_success
        call["error_kind"] = decision.result.error_kind.value if decision.result.error_kind else None
        call["message"] = decision.result.message
        call["raw_output"] = decision.result.raw_output
        if not decision.result.is_success or decision.result.action is None:
            return None, [call], decision.result.message or "visual_policy_failed"
        normalized = decision.result.action.parameters["point"]
        point = normalized_to_pixels(normalized, image.size)
        return GroundingCandidate(point, GroundingSource.VISION, 0.55, "GUI-Plus visual candidate."), [call], ""

    def _setup(self, name: str) -> None:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                self._setup_once(name)
                return
            except Exception as exc:
                last_error = exc
                time.sleep(0.35)
        raise RuntimeError(f"experiment setup failed after 3 attempts: {name}: {last_error}") from last_error

    def _setup_once(self, name: str) -> None:
        self.device.app_start(PACKAGE, ".MainActivity", stop=True)
        if not self.device.app_wait(PACKAGE, front=True, timeout=10):
            raise RuntimeError("MobilePilot Lab did not become foreground")
        if name == "home":
            return
        if name == "home_prefilled":
            field = self.device(resourceId=f"{PACKAGE}:id/search_input")
            if not field.wait(timeout=5):
                raise RuntimeError("search input missing during setup")
            field.set_text("coffee")
            return
        if name == "test_dialog":
            self.device(resourceId=f"{PACKAGE}:id/debug_dialog_button").click()
            if not self.device(text="关闭").wait(timeout=5):
                raise RuntimeError("test dialog did not appear")
            return
        if name == "visual_dialog":
            self.device.click(630, 1333)
            if not self.device(text="视觉定位验证成功").wait(timeout=5):
                raise RuntimeError("visual success dialog did not appear")
            return
        if name == "results":
            field = self.device(resourceId=f"{PACKAGE}:id/search_input")
            if not field.wait(timeout=5):
                raise RuntimeError("search input missing during results setup")
            field.set_text("coffee")
            self.device(resourceId=f"{PACKAGE}:id/search_button").click()
            if not self.device(resourceId=f"{PACKAGE}:id/filter_button").wait(timeout=5):
                raise RuntimeError("results page did not appear")
            return
        raise ValueError(f"unknown setup: {name}")


def add_grid(image: Image.Image, columns: int, rows: int) -> Image.Image:
    if columns < 2 or rows < 2:
        raise ValueError("grid dimensions must be at least 2")
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = base.size
    line_width = max(2, min(4, int(min(width, height) * 0.003)))
    for column in range(1, columns):
        x = int(width * column / columns)
        draw.line((x, 0, x, height), fill=(0, 180, 255, 90), width=line_width)
    for row in range(1, rows):
        y = int(height * row / rows)
        draw.line((0, y, width, y), fill=(0, 180, 255, 90), width=line_width)
    return Image.alpha_composite(base, overlay).convert("RGB")


def crop_around(
    image_size: tuple[int, int],
    point: tuple[int, int],
    *,
    width_ratio: float = 0.60,
    height_ratio: float = 0.45,
) -> tuple[int, int, int, int]:
    width, height = image_size
    crop_width = max(1, int(width * width_ratio))
    crop_height = max(1, int(height * height_ratio))
    left = min(max(0, point[0] - crop_width // 2), width - crop_width)
    top = min(max(0, point[1] - crop_height // 2), height - crop_height)
    return (left, top, left + crop_width, top + crop_height)


def normalized_to_pixels(value: list[int], image_size: tuple[int, int]) -> tuple[int, int]:
    width, height = image_size
    return (min(width - 1, int(value[0] / 1000 * width)), min(height - 1, int(value[1] / 1000 * height)))


def _tree_auxiliary_check(point: tuple[int, int], task: TaskSpec, state: ScreenState) -> tuple[bool, str]:
    containing = [element for element in state.elements if element.enabled and _contains(element.bounds, point)]
    if task.target_resource_id and any(element.resource_id == task.target_resource_id for element in containing):
        return False, ""
    conflicts = [element for element in containing if element.clickable]
    if conflicts:
        label = conflicts[0].resource_id or conflicts[0].text or conflicts[0].content_description
        return True, f"tree_aux_conflict:{label}"
    return False, ""


def _contains(bounds: tuple[int, int, int, int], point: tuple[int, int]) -> bool:
    left, top, right, bottom = bounds
    return left <= point[0] < right and top <= point[1] < bottom


def _image_change_score(before: Image.Image, after: Image.Image) -> float:
    if before.size != after.size:
        return 255.0
    difference = ImageStat.Stat(_difference(before.convert("RGB"), after.convert("RGB"))).mean
    return sum(difference) / len(difference)


def _difference(before: Image.Image, after: Image.Image) -> Image.Image:
    from PIL import ImageChops

    return ImageChops.difference(before, after)


def _sum_present(calls: list[dict[str, Any]], key: str) -> int | float | None:
    values = [call[key] for call in calls if call.get(key) is not None]
    return sum(values) if values else None


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _completed_keys(path: Path) -> set[tuple[str, str, int]]:
    return {(row["task_id"], row["config"], int(row["repeat"])) for row in _read_jsonl(path)}


def _write_summaries(records: list[dict[str, Any]], output_dir: Path) -> None:
    by_config: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_config.setdefault(record["config"], []).append(record)

    summary = []
    for config, rows in sorted(by_config.items()):
        calls = sum(row["model_call_count"] for row in rows)
        prompt_tokens = sum(row["prompt_tokens"] or 0 for row in rows)
        completion_tokens = sum(row["completion_tokens"] or 0 for row in rows)
        costs = [row["estimated_list_cost_cny"] for row in rows if row["estimated_list_cost_cny"] is not None]
        audited_successes = sum(_audited_task_success(row) for row in rows)
        step_successes = sum(bool(row["candidate_correct"] and row["executed"]) for row in rows)
        wrong_clicks = sum(row["wrong_click"] for row in rows)
        executed = sum(row["executed"] for row in rows)
        summary.append({
            "config": config,
            "runs": len(rows),
            "task_success_rate": audited_successes / len(rows),
            "strict_screenshot_task_success_rate": sum(row["task_success"] for row in rows) / len(rows),
            "step_success_rate": step_successes / len(rows),
            "wrong_click_rate_per_run": wrong_clicks / len(rows),
            "wrong_click_rate_per_executed_action": wrong_clicks / executed if executed else 0.0,
            "critic_block_rate": sum(row["critic_blocked"] for row in rows) / len(rows),
            "verifier_false_negative_count": sum(_is_filter_verifier_false_negative(row) for row in rows),
            "model_call_count": calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_list_cost_cny": sum(costs) if costs else None,
            "mean_model_latency_seconds": statistics.mean(row["model_latency_seconds"] for row in rows),
            "mean_run_latency_seconds": statistics.mean(row["run_latency_seconds"] for row in rows),
            "failures": _failure_counts(rows),
        })

    with (output_dir / "summary.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    csv_fields = [key for key in summary[0] if key != "failures"] if summary else []
    with (output_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in csv_fields} for row in summary)

    task_ids = sorted({record["task_id"] for record in records})
    config_names = sorted(by_config)
    with (output_dir / "task_matrix.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["task_id", *config_names])
        writer.writeheader()
        for task_id in task_ids:
            row: dict[str, Any] = {"task_id": task_id}
            for config in config_names:
                matches = [record for record in by_config[config] if record["task_id"] == task_id]
                row[config] = f"{sum(_audited_task_success(record) for record in matches)}/{len(matches)}"
            writer.writerow(row)


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if _is_filter_verifier_false_negative(row):
            reason = "success_after_verifier_audit"
        else:
            reason = row["failure_reason"] or "success"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _is_filter_verifier_false_negative(row: dict[str, Any]) -> bool:
    return bool(
        row["task_id"] == "results_filter"
        and row["failure_reason"] == "post_action_screen_unchanged"
        and row["candidate_correct"]
        and row["executed"]
    )


def _audited_task_success(row: dict[str, Any]) -> bool:
    return bool(row["task_success"] or _is_filter_verifier_false_negative(row))


def _select(values: str, items: Iterable[Any], key: str) -> tuple[Any, ...]:
    items = tuple(items)
    if not values:
        return items
    requested = {value.strip() for value in values.split(",") if value.strip()}
    selected = tuple(item for item in items if getattr(item, key) in requested)
    missing = requested - {getattr(item, key) for item in selected}
    if missing:
        raise ValueError(f"unknown selection: {sorted(missing)}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MobilePilot visual mainline matrix on MobilePilot Lab.")
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--tasks", default="", help="comma-separated task ids")
    parser.add_argument("--configs", default="", help="comma-separated config names")
    args = parser.parse_args()
    if not args.serial:
        raise ValueError("serial is required; pass --serial or set ANDROID_SERIAL")
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    tasks = _select(args.tasks, TASKS, "task_id")
    configs = _select(args.configs, EXPERIMENT_CONFIGS, "name")
    VisualMatrixRunner(args.serial, args.output).run(repeats=args.repeats, tasks=tasks, configs=configs)


if __name__ == "__main__":
    main()
