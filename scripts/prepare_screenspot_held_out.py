"""Download and audit the frozen 471 ScreenSpot-v2 Mobile held-out images."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import urllib.request

from PIL import Image

from mobile_pilot.evaluation.screenspot.dataset import (
    attach_voxel_image_paths,
    build_integration_split,
    load_official_mobile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "artifacts/evaluation/screenspot-v2-20260723"
HELD_OUT_MANIFEST = BENCHMARK_ROOT / "manifests/held_out_manifest.json"
INTEGRATION_MANIFEST = BENCHMARK_ROOT / "manifests/integration_audit_manifest.json"
MAPPING_OUTPUT = BENCHMARK_ROOT / "manifests/held_out_image_mapping.json"
PROVENANCE_OUTPUT = BENCHMARK_ROOT / "held-out/image_provenance.json"
ANNOTATION_PATH = PROJECT_ROOT / "data/screenspot-v2/screenspot_mobile_v2.json"
VOXEL_SAMPLES_PATH = PROJECT_ROOT / "data/screenspot-v2/voxel51_samples.json"
IMAGE_DIR = PROJECT_ROOT / "data/screenspot-v2/held-out-images"

REPOSITORY = "Voxel51/ScreenSpot-v2"
COMMIT = "f221b744a2e73f64d5178a0548db8e667c4843e0"
EXPECTED_MANIFEST_SHA256 = "719cdb167c12d3416499c0cf70dfbac480c142dd0e56b6a52f9ada52d322021d"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    if target.is_file():
        return
    temporary = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "MobilePilot/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        temporary.write_bytes(response.read())
    temporary.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if sha256_file(HELD_OUT_MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("frozen held-out manifest hash mismatch")
    frozen_held_out = json.loads(HELD_OUT_MANIFEST.read_text(encoding="utf-8"))
    frozen_integration = json.loads(INTEGRATION_MANIFEST.read_text(encoding="utf-8"))
    if len(frozen_held_out) != 471:
        raise ValueError("expected 471 frozen held-out rows")
    if {row["sample_id"] for row in frozen_held_out} & {
        row["sample_id"] for row in frozen_integration
    }:
        raise ValueError("integration/held-out overlap detected")

    all_samples = load_official_mobile(ANNOTATION_PATH)
    integration, held_out = build_integration_split(all_samples)
    if [sample.sample_id for sample in held_out] != [
        row["sample_id"] for row in frozen_held_out
    ]:
        raise ValueError("reconstructed held-out split differs from frozen manifest")
    if {sample.sample_id for sample in integration} != {
        row["sample_id"] for row in frozen_integration
    }:
        raise ValueError("reconstructed integration split differs from frozen manifest")

    mapped = attach_voxel_image_paths(
        held_out,
        VOXEL_SAMPLES_PATH,
        local_image_dir=IMAGE_DIR,
    )
    repository_paths = [sample.image_repository_path for sample in mapped]
    local_names = [sample.image_path.name for sample in mapped if sample.image_path]
    if len(repository_paths) != len(set(repository_paths)):
        raise ValueError("repository image signatures are not unique")
    if len(local_names) != len(set(local_names)):
        raise ValueError("local image filenames are not unique")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for sample in mapped:
            relative = sample.image_repository_path.replace("\\", "/")
            url = f"https://hf-mirror.com/datasets/{REPOSITORY}/resolve/{COMMIT}/{relative}"
            jobs.append(executor.submit(download, url, sample.image_path))
        for index, future in enumerate(as_completed(jobs), start=1):
            future.result()
            if index % 25 == 0 or index == len(jobs):
                print(f"downloaded_or_present={index}/{len(jobs)}", flush=True)

    rows = []
    for sample in mapped:
        with Image.open(sample.image_path) as image:
            image.verify()
        with Image.open(sample.image_path) as image:
            width, height = image.size
        x, y, box_width, box_height = sample.bbox_xywh
        if x < 0 or y < 0 or box_width <= 0 or box_height <= 0:
            raise ValueError(f"invalid bbox: {sample.sample_id}")
        if x + box_width > width or y + box_height > height:
            raise ValueError(f"bbox outside image: {sample.sample_id}")
        rows.append(
            {
                "sample_id": sample.sample_id,
                "image_repository_path": sample.image_repository_path,
                "local_path": sample.image_path.relative_to(PROJECT_ROOT).as_posix(),
                "image_size": [width, height],
                "sha256": sha256_file(sample.image_path),
            }
        )

    MAPPING_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MAPPING_OUTPUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    PROVENANCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    provenance = {
        "benchmark": "ScreenSpot-v2 Mobile",
        "subset": "held_out",
        "samples": len(rows),
        "source_repository": REPOSITORY,
        "source_commit": COMMIT,
        "download_base": f"https://hf-mirror.com/datasets/{REPOSITORY}/resolve/{COMMIT}/",
        "held_out_manifest_sha256": sha256_file(HELD_OUT_MANIFEST),
        "integration_manifest_sha256": sha256_file(INTEGRATION_MANIFEST),
        "mapping_sha256": sha256_file(MAPPING_OUTPUT),
        "image_checks": {
            "present": len(rows),
            "openable": len(rows),
            "valid_bbox": len(rows),
            "unique_repository_paths": len(set(repository_paths)),
            "unique_local_paths": len(set(local_names)),
            "integration_overlap": 0,
        },
    }
    PROVENANCE_OUTPUT.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(provenance, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
