from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT.parent
OS_ROOT = Path(os.environ.get("UNILAB_OS_ROOT", CORE_ROOT / "Uni-Lab-OS"))

for path in (OS_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def package_catalog(repo_root: Path):
    from unilabos.package_manager import WorkspaceSource, compile_package_source

    return compile_package_source(WorkspaceSource(repo_root))


@pytest.fixture(scope="session")
def production_registry(package_catalog):
    """Build the same core HostNode + selected package registry used by OS."""
    from unilabos.registry.registry import Registry

    registry = Registry()
    registry.device_type_registry = {}
    registry.resource_type_registry = {}
    registry._setup_called = False
    registry.setup(
        external_only=True,
        package_catalogs=[package_catalog],
    )
    return registry


@pytest.fixture()
def production_authoring_service(
    repo_root: Path,
    package_catalog,
    production_registry,
    tmp_path: Path,
):
    """Compose the real OS authoring catalog, inventory, and framework templates."""
    from unilabos.package_manager import WorkspaceSource
    from unilabos.resources.graphio import read_node_link_json
    from unilabos.workflow.catalog import CatalogAuthority
    from unilabos.workflow.composition import (
        compose_workflow_runtime,
        reset_workflow_service_for_test,
    )

    reset_workflow_service_for_test()
    graph_path = repo_root / "deployment" / "graphs" / "szlab-local-debug.json"
    _graph, resource_tree_set, _links = read_node_link_json(str(graph_path))
    inventory_snapshot = {
        "source_id": graph_path.name,
        "nodes": [
            node.res_content.model_dump(by_alias=True)
            for node in resource_tree_set.all_nodes
        ],
    }
    source = WorkspaceSource(repo_root)
    service = compose_workflow_runtime(
        tmp_path / "workflow-authority",
        authority=CatalogAuthority("szlab-production-test", "local"),
        registry_snapshot=production_registry.device_type_registry,
        resource_registry_snapshot=production_registry.resource_type_registry,
        workflow_package_catalogs=(package_catalog,),
        inventory_graph_snapshot=inventory_snapshot,
        package_sources=(source,),
        package_catalogs=(package_catalog,),
    )
    try:
        assert service.compiler is not None
        yield service
    finally:
        reset_workflow_service_for_test()


@pytest.fixture()
def production_authoring_compiler(production_authoring_service):
    yield production_authoring_service.compiler


@pytest.fixture(scope="session")
def action_catalog(package_catalog) -> dict:
    from unilabos.package_manager.consumers import (
        action_catalog_from_package_catalog,
    )

    return action_catalog_from_package_catalog(package_catalog)
