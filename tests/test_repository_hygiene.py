from __future__ import annotations

import json
from pathlib import Path


def test_szlab_debug_graph_uses_only_registered_project_classes(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    payload = json.loads(
        (repo_root / "deployment" / "graphs" / "szlab-local-debug.json").read_text(
            encoding="utf-8"
        )
    )
    ids = [node["id"] for node in payload["nodes"]]
    assert len(ids) == len(set(ids))
    assert payload["links"] == []

    device_classes = {
        ref.split(".", 1)[0]
        for ref in action_catalog
        if not ref.startswith("szlab_poly_studio.")
    }
    graph_device_classes = {
        node["class"] for node in payload["nodes"] if node["type"] == "device"
    }
    assert graph_device_classes <= device_classes
    assert all(not node["class"].casefold().startswith("ai4c") for node in payload["nodes"])
    assert all(
        node.get("config", {}).get("auto_connect") is False
        for node in payload["nodes"]
        if node["class"] == "szlab_poly_plc"
    )
    unified_plc_device_classes = {
        "szlab_mixer_robot",
        "szlab_mixer_stirrer",
        "szlab_mixer_photoshotting",
        "szlab_mixer_pump",
        "szlab_s07_solid_addition",
        "szlab_s08_cap_station",
        "szlab_mixer_pipetting_station",
    }
    for node in payload["nodes"]:
        if node["class"] not in unified_plc_device_classes:
            continue
        config = node.get("config", {})
        assert config.get("plc_device_id") == "szlab_poly_plc"
        assert "url" not in config
        assert "csv_path" not in config
        assert "auto_connect" not in config


def test_repository_is_one_distribution_with_one_import_package(repo_root: Path) -> None:
    assert not (repo_root / "packages").exists()
    assert (repo_root / "pyproject.toml").is_file()
    assert (repo_root / "szlab_poly_studio" / "__init__.py").is_file()

    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "szlab-poly-studio"' in pyproject
    assert 'include = ["szlab_poly_studio*"]' in pyproject
    assert "unilabos.model_bundles" not in pyproject


def test_szlab_source_does_not_cross_import_ai4c(repo_root: Path) -> None:
    violations = [
        str(path.relative_to(repo_root))
        for path in (repo_root / "szlab_poly_studio").rglob("*.py")
        if "ai4c_robot" in path.read_text(encoding="utf-8").casefold()
    ]
    assert violations == []


def test_production_sources_do_not_contain_legacy_paths_or_model_bundle_protocol(
    repo_root: Path,
) -> None:
    forbidden = (
        "unilabos.devices.workstation.szlab_poly_studio",
        "unilabos.model_bundles",
        "model_bundle",
        "/Users/",
        "auto_prefix=True",
        "auto_prefix = True",
    )
    violations: list[str] = []
    for path in (repo_root / "szlab_poly_studio").rglob("*"):
        if path.suffix not in {".py", ".yaml", ".toml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(repo_root)}: {marker}")
    assert violations == []
