from __future__ import annotations

import json
from pathlib import Path


def test_local_debug_graph_uses_only_registered_project_classes(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    payload = json.loads((repo_root / "deployment" / "graphs" / "local-debug.json").read_text(encoding="utf-8"))
    ids = [node["id"] for node in payload["nodes"]]
    assert len(ids) == len(set(ids))
    assert payload["links"] == []

    device_classes = {
        ref.split(".", 1)[0] for ref in action_catalog if not ref.startswith(("szlab_poly_studio.", "ai4c_station."))
    }
    graph_device_classes = {node["class"] for node in payload["nodes"] if node["type"] == "device"}
    assert graph_device_classes <= device_classes
    assert all(
        node.get("config", {}).get("auto_connect") is False
        for node in payload["nodes"]
        if node["class"]
        in {
            "szlab_poly_plc",
            "szlab_mixer_stirrer",
            "szlab_mixer_photoshotting",
            "szlab_mixer_pump",
            "szlab_s08_cap_station",
            "szlab_mixer_pipetting_station",
            "AI4C_plc",
        }
    )


def test_package_specific_debug_graphs_are_fully_separated(repo_root: Path) -> None:
    graph_root = repo_root / "deployment" / "graphs"
    combined = json.loads((graph_root / "local-debug.json").read_text(encoding="utf-8"))
    szlab = json.loads((graph_root / "szlab-local-debug.json").read_text(encoding="utf-8"))
    ai4c = json.loads((graph_root / "ai4c-local-debug.json").read_text(encoding="utf-8"))

    combined_ids = {node["id"] for node in combined["nodes"]}
    szlab_ids = {node["id"] for node in szlab["nodes"]}
    ai4c_ids = {node["id"] for node in ai4c["nodes"]}

    assert len(szlab_ids) == 22
    assert len(ai4c_ids) == 2
    assert szlab_ids.isdisjoint(ai4c_ids)
    assert szlab_ids | ai4c_ids == combined_ids
    assert all(not node["class"].startswith("AI4C") for node in szlab["nodes"])
    assert all(node["class"].startswith("AI4C") for node in ai4c["nodes"])
    assert szlab["links"] == ai4c["links"] == []


def test_python_distributions_do_not_cross_import(repo_root: Path) -> None:
    package_sources = {
        "szlab_poly_studio": repo_root / "packages" / "szlab_poly_studio" / "szlab_poly_studio",
        "ai4c_robot": repo_root / "packages" / "ai4c_robot" / "ai4c_robot",
    }
    for package_name, source_root in package_sources.items():
        other_package = next(name for name in package_sources if name != package_name)
        violations = [
            str(path.relative_to(repo_root))
            for path in source_root.rglob("*.py")
            if other_package in path.read_text(encoding="utf-8")
        ]
        assert violations == []


def test_production_sources_do_not_contain_legacy_paths_or_auto_action_prefix(repo_root: Path) -> None:
    forbidden = (
        "unilabos.devices.workstation.szlab_poly_studio",
        "/Users/",
        "auto_prefix=True",
        "auto_prefix = True",
    )
    violations: list[str] = []
    for path in (repo_root / "packages").rglob("*"):
        if path.suffix not in {".py", ".yaml", ".toml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(repo_root)}: {marker}")
    assert violations == []
