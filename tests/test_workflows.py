from __future__ import annotations

import json
from pathlib import Path

import yaml
from unilabos.workflow.from_python_script import compile_python_script


def _manifest_entries(manifest: dict) -> list[dict]:
    return [*manifest["presets"], *manifest["additional_workflows"]]


def test_migration_manifest_covers_all_committed_inputs(repo_root: Path) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))
    presets = manifest["presets"]

    assert len(presets) == 12
    assert {item["id"] for item in presets} == {
        path.stem for path in (migration_root / "legacy" / "ui-presets").glob("*.json")
    }
    assert {item["legacy_workflow"] for item in _manifest_entries(manifest) if item.get("legacy_workflow")} == {
        str(path.relative_to(migration_root)) for path in (migration_root / "legacy" / "workflows").glob("*.json")
    }
    assert manifest["capture"]["live_browser_draft_found"] is False

    for entry in _manifest_entries(manifest):
        assert (migration_root / entry["python_source"]).resolve().is_file()
        assert (migration_root / entry.get("legacy_preset", "manifest.yaml")).resolve().is_file()
        if entry.get("legacy_workflow"):
            assert (migration_root / entry["legacy_workflow"]).resolve().is_file()


def test_all_migrated_python_workflows_compile_to_canonical_v2(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))
    compiled_ids: set[str] = set()

    for entry in _manifest_entries(manifest):
        source_path = (migration_root / entry["python_source"]).resolve()
        revision = compile_python_script(
            source_path.read_text(encoding="utf-8"),
            action_catalog=action_catalog,
        )
        assert revision.workflow_id == entry["workflow_id"]
        assert revision.invocations
        assert len(revision.source_map.entries) == len(revision.invocations)
        assert all(invocation.action_ref in action_catalog for invocation in revision.invocations)
        compiled_ids.add(revision.workflow_id)

    assert len(compiled_ids) == 13


def test_legacy_json_action_sequences_are_preserved(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))

    for entry in _manifest_entries(manifest):
        legacy_ref = entry.get("legacy_workflow")
        if not legacy_ref:
            continue
        legacy = json.loads((migration_root / legacy_ref).read_text(encoding="utf-8"))
        expected = [f"{node['device_name']}.{node['name'].removeprefix('auto-')}" for node in legacy["nodes"]]
        if entry["workflow_id"] == "s08_cap_workflow":
            expected = ["szlab_s08_cap_station.process_cap_with_sample_parts" for _ in expected]

        source_path = (migration_root / entry["python_source"]).resolve()
        revision = compile_python_script(
            source_path.read_text(encoding="utf-8"),
            action_catalog=action_catalog,
        )
        assert [invocation.action_ref for invocation in revision.invocations] == expected


def test_e2e_screenshots_cover_every_production_workflow(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    result_path = repo_root / "docs" / "screenshots" / "all-workflows-e2e-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["outcome"] == "passed"
    assert result["total"] == 13
    assert result["packages"] == {"SZLab": 12, "AI4C": 1}
    assert result["browserErrors"] == []
    assert [item["order"] for item in result["workflows"]] == list(range(1, 14))

    compiled_ids: set[str] = set()
    for item in result["workflows"]:
        source_path = repo_root / item["source"]
        screenshot_path = repo_root / "docs" / "screenshots" / item["screenshot"]
        revision = compile_python_script(
            source_path.read_text(encoding="utf-8"),
            action_catalog=action_catalog,
        )

        assert revision.workflow_id == item["workflow_id"]
        assert len(revision.invocations) == item["node_count"]
        assert len(revision.control_edges) == item["edge_count"]
        assert screenshot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert screenshot_path.stat().st_size > 100_000
        compiled_ids.add(revision.workflow_id)

    assert len(compiled_ids) == 13
