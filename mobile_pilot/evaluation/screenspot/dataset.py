"""ScreenSpot-v2 Mobile 官方标注解析与固定审计集划分。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


OFFICIAL_DATASET_REPOSITORY = "OS-Copilot/ScreenSpot-v2"
OFFICIAL_DATASET_COMMIT = "5efbb1f1b5463a575f2eb7bc30fe29e49c15f93c"
OFFICIAL_MOBILE_JSON_SHA256 = "fdd1595b64179e31407eed5929fa12e80adc6ba2ee372a3802d36da379ea1825"
PAPER_REPORTED_MOBILE_COUNT = 502
RELEASED_MOBILE_COUNT = 501


@dataclass(frozen=True)
class ScreenSpotSample:
    index: int
    sample_id: str
    img_filename: str
    bbox_xywh: tuple[int, int, int, int]
    instruction: str
    data_type: str
    data_source: str
    image_path: Path | None = None
    image_repository_path: str | None = None
    subset: str = "unassigned"

    @property
    def bbox_xyxy(self) -> tuple[int, int, int, int]:
        x, y, width, height = self.bbox_xywh
        return (x, y, x + width, y + height)

    def to_manifest_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["bbox_xywh"] = list(self.bbox_xywh)
        row["bbox_xyxy"] = list(self.bbox_xyxy)
        row["image_path"] = str(self.image_path) if self.image_path else None
        return row


def load_official_mobile(
    annotation_path: Path,
    *,
    image_dir: Path | None = None,
    verify_sha256: bool = True,
) -> list[ScreenSpotSample]:
    """解析官方 ``screenspot_mobile_v2.json``。

    官方发布文件中的 ``bbox`` 是像素 ``[x, y, width, height]``。这一点也可由
    FiftyOne 转换版的归一化 ``[x, y, width, height]`` 与图片尺寸逐条反算验证。
    """

    payload = annotation_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if verify_sha256 and digest != OFFICIAL_MOBILE_JSON_SHA256:
        raise ValueError(f"unexpected ScreenSpot-v2 Mobile JSON sha256: {digest}")
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("ScreenSpot-v2 Mobile annotations must be a JSON list")

    samples: list[ScreenSpotSample] = []
    for index, row in enumerate(rows):
        _validate_row(row, index)
        bbox = tuple(int(value) for value in row["bbox"])
        stable = json.dumps(
            [row["img_filename"], row["instruction"], row["data_type"], row["data_source"], bbox],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        sample_id = f"mobile-{index:04d}-{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:10]}"
        samples.append(
            ScreenSpotSample(
                index=index,
                sample_id=sample_id,
                img_filename=row["img_filename"],
                bbox_xywh=bbox,
                instruction=row["instruction"],
                data_type=row["data_type"],
                data_source=row["data_source"],
                image_path=image_dir / row["img_filename"] if image_dir else None,
            )
        )
    return samples


def build_integration_split(
    samples: Iterable[ScreenSpotSample],
    *,
    per_type: int = 15,
    seed: str = "mobilepilot-screenspot-v2-integration-audit-v1",
) -> tuple[list[ScreenSpotSample], list[ScreenSpotSample]]:
    """固定 30 条 integration/audit subset，并返回其余 held-out。

    每个 ``data_type`` 内对 ios/android/shop 等来源轮询抽样；排序只依赖公开字段和
    固定 seed，不依赖模型结果。
    """

    samples = list(samples)
    selected_ids: set[str] = set()
    for data_type in ("text", "icon"):
        group = [sample for sample in samples if sample.data_type == data_type]
        sources = sorted({sample.data_source for sample in group})
        if not sources:
            raise ValueError(f"missing samples for data_type={data_type}")
        buckets = {
            source: sorted(
                (sample for sample in group if sample.data_source == source),
                key=lambda sample: _selection_key(seed, sample),
            )
            for source in sources
        }
        cursor = {source: 0 for source in sources}
        while sum(sample_id in selected_ids for sample_id in (sample.sample_id for sample in group)) < per_type:
            progressed = False
            for source in sources:
                position = cursor[source]
                if position >= len(buckets[source]):
                    continue
                selected_ids.add(buckets[source][position].sample_id)
                cursor[source] += 1
                progressed = True
                if sum(sample_id in selected_ids for sample_id in (sample.sample_id for sample in group)) >= per_type:
                    break
            if not progressed:
                raise ValueError(f"not enough samples for data_type={data_type}")

    integration = [replace(sample, subset="integration_audit") for sample in samples if sample.sample_id in selected_ids]
    held_out = [replace(sample, subset="held_out") for sample in samples if sample.sample_id not in selected_ids]
    if len(integration) != per_type * 2:
        raise AssertionError(f"expected {per_type * 2} integration samples, got {len(integration)}")
    return integration, held_out


def attach_voxel_image_paths(
    samples: Iterable[ScreenSpotSample],
    voxel_samples_path: Path,
    *,
    local_image_dir: Path,
) -> list[ScreenSpotSample]:
    """将公开 FiftyOne 转换版的逐样本图片路径映射回官方标注。

    映射使用 instruction/source/type/bbox 的完整签名；不依赖列表顺序或模型结果。
    """

    payload = json.loads(voxel_samples_path.read_text(encoding="utf-8"))
    mapping: dict[tuple[Any, ...], str] = {}
    for row in payload["samples"]:
        if not Path(row["filepath"]).name.startswith("mobile_"):
            continue
        metadata = row["metadata"]
        normalized = row["action_detection"]["bounding_box"]
        bbox = tuple(
            round(value * scale)
            for value, scale in zip(
                normalized,
                (metadata["width"], metadata["height"], metadata["width"], metadata["height"]),
            )
        )
        signature = (
            row["instruction"].strip(),
            row["data_source"]["label"],
            row["action_detection"]["label"],
            bbox,
        )
        mapping[signature] = row["filepath"].replace("\\", "/")

    attached = []
    for sample in samples:
        signature = (
            sample.instruction.strip(),
            sample.data_source,
            sample.data_type,
            sample.bbox_xywh,
        )
        repository_path = mapping.get(signature)
        if not repository_path:
            raise ValueError(f"no image mapping for {sample.sample_id}")
        attached.append(
            replace(
                sample,
                image_repository_path=repository_path,
                image_path=local_image_dir / Path(repository_path).name,
            )
        )
    return attached


def write_split_manifests(
    integration: Iterable[ScreenSpotSample],
    held_out: Iterable[ScreenSpotSample],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, samples in (("integration_audit", integration), ("held_out", held_out)):
        rows = [sample.to_manifest_row() for sample in samples]
        (output_dir / f"{name}_manifest.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_manifest(path: Path) -> list[ScreenSpotSample]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    samples = []
    for row in rows:
        samples.append(
            ScreenSpotSample(
                index=int(row["index"]),
                sample_id=row["sample_id"],
                img_filename=row["img_filename"],
                bbox_xywh=tuple(int(value) for value in row["bbox_xywh"]),
                instruction=row["instruction"],
                data_type=row["data_type"],
                data_source=row["data_source"],
                image_path=Path(row["image_path"]) if row.get("image_path") else None,
                image_repository_path=row.get("image_repository_path"),
                subset=row["subset"],
            )
        )
    return samples


def _selection_key(seed: str, sample: ScreenSpotSample) -> str:
    return hashlib.sha256(f"{seed}|{sample.sample_id}".encode("utf-8")).hexdigest()


def _validate_row(row: Any, index: int) -> None:
    required = {"img_filename", "bbox", "instruction", "data_type", "data_source"}
    if not isinstance(row, dict) or not required.issubset(row):
        raise ValueError(f"invalid ScreenSpot row at index {index}")
    if row["data_type"] not in {"text", "icon"}:
        raise ValueError(f"unsupported data_type at index {index}: {row['data_type']}")
    bbox = row["bbox"]
    if not isinstance(bbox, list) or len(bbox) != 4 or any(isinstance(value, bool) or not isinstance(value, int) for value in bbox):
        raise ValueError(f"invalid bbox at index {index}: {bbox}")
    if bbox[2] <= 0 or bbox[3] <= 0:
        raise ValueError(f"non-positive bbox at index {index}: {bbox}")
