from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from unilabos.package_manager import PackageCatalog


def test_szlab_graphs_use_only_catalog_definitions(
    repo_root: Path,
    package_catalog: PackageCatalog,
) -> None:
    catalog_classes = {
        definition.fqid
        for collection in (
            package_catalog.definitions.devices,
            package_catalog.definitions.resources,
        )
        for definition in collection
    }
    for graph_path in sorted((repo_root / "deployment" / "graphs").glob("szlab-*.json")):
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        ids = [node["id"] for node in payload["nodes"]]
        assert len(ids) == len(set(ids)), graph_path.name
        assert set(node["class"] for node in payload["nodes"]) <= catalog_classes
        assert all(node["class"].startswith("community.szlab_poly_studio.") for node in payload["nodes"])


def test_szlab_graph_owns_connection_configuration(repo_root: Path) -> None:
    payload = json.loads((repo_root / "deployment" / "graphs" / "szlab-local-debug.json").read_text(encoding="utf-8"))
    assert payload["links"] == []
    assert all(not node["class"].casefold().startswith("ai4c") for node in payload["nodes"])
    plc = next(node for node in payload["nodes"] if node["id"] == "szlab_poly_plc")
    assert plc["config"]["url"] == "opc.tcp://127.0.0.1:50100/"
    assert plc["config"]["csv_path"] == "szlab_plc_0730.csv"
    assert plc["config"]["auto_connect"] is False

    unified_plc_device_ids = {
        "szlab_mixer_robot",
        "szlab_mixer_stirrer",
        "szlab_mixer_photoshotting",
        "szlab_mixer_pump",
        "szlab_s07_solid_addition",
        "szlab_s08_cap_station",
        "szlab_mixer_pipetting_station",
    }
    for node in payload["nodes"]:
        if node["id"] not in unified_plc_device_ids:
            continue
        config = node.get("config", {})
        assert config.get("plc_device_id") == "szlab_poly_plc"
        assert "url" not in config
        assert "csv_path" not in config
        assert "auto_connect" not in config


def test_every_graph_config_matches_its_catalog_init_schema(
    repo_root: Path,
    package_catalog: PackageCatalog,
    monkeypatch,
) -> None:
    from unilabos.package_manager.consumers import register_package_catalog
    from unilabos.registry.registry import lab_registry

    monkeypatch.setattr(lab_registry, "device_type_registry", {})
    monkeypatch.setattr(lab_registry, "resource_type_registry", {})
    register_package_catalog(lab_registry, package_catalog)

    for graph_path in sorted((repo_root / "deployment" / "graphs").glob("szlab-*.json")):
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in payload["nodes"]:
            registry = (
                lab_registry.device_type_registry if node["type"] == "device" else lab_registry.resource_type_registry
            )
            schema = (registry[node["class"]].get("init_param_schema") or {}).get("config")
            if schema is not None:
                Draft202012Validator(schema).validate(node.get("config") or {})


def test_repository_is_one_distribution_with_one_import_package(repo_root: Path) -> None:
    assert not (repo_root / "packages").exists()
    assert (repo_root / "pyproject.toml").is_file()
    assert (repo_root / "szlab_poly_studio" / "__init__.py").is_file()

    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "szlab-poly-studio"' in pyproject
    assert 'include = ["szlab_poly_studio*"]' in pyproject
    assert "unilabos.model_bundles" not in pyproject


def test_repository_has_no_runtime_profile_protocol(repo_root: Path) -> None:
    assert not (repo_root / "szlab_poly_studio" / "profiles").exists()
    assert not (repo_root / "schemas" / "profile-v1.schema.json").exists()
    assert not (repo_root / "schemas" / "device-template-v2.schema.json").exists()


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
