import json

import pytest

from mobile_pilot.androidworld.held_out import assert_registry_contains, load_held_out_manifest


def test_loads_frozen_held_out_manifest_without_development_overlap():
    manifest = load_held_out_manifest("configs/androidworld/held_out_20.json")

    assert len(manifest.tasks) == 20
    assert manifest.task_id_sha256 == "6971ef742428b670bff560648dd4502d5f59a368b96d7402a0a4fdddad3d0fa8"
    assert not set(manifest.task_ids) & set(manifest.development_task_exclusions)


def test_rejects_mutated_order_even_when_task_count_is_unchanged(tmp_path):
    source = json.loads(open("configs/androidworld/held_out_20.json", encoding="utf-8").read())
    source["tasks"][0], source["tasks"][1] = source["tasks"][1], source["tasks"][0]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="hash"):
        load_held_out_manifest(path)


def test_rejects_manifest_task_missing_from_registry():
    manifest = load_held_out_manifest("configs/androidworld/held_out_20.json")

    with pytest.raises(ValueError, match="missing"):
        assert_registry_contains(manifest, manifest.task_ids[:-1])
