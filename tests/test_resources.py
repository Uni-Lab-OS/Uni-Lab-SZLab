from __future__ import annotations

import json
from pathlib import Path

from szlab_poly_studio.resources.decks import SZLabPolyStudioDeck
from szlab_poly_studio.resources.materials import (
    beaker_500ml,
    liquid_reagent_bottle_100ml,
    pipette_tip,
    powder_container,
    sample_vial_250ml,
    sample_vial_500ml,
)
from szlab_poly_studio.resources.warehouses import (
    powder_container_placeholder_warehouse,
    s1_loading_buffer_warehouse,
    s2_tip_placeholder_warehouse,
    s3_unused_beaker_warehouse,
    s3_unused_sample_vial_warehouse,
    s10_liquid_reagent_placeholder_warehouse,
    s11_used_beaker_warehouse,
    s11_used_sample_vial_warehouse,
)


def test_warehouse_site_counts_and_keys() -> None:
    warehouses = {
        # tip 盒上料工装：2 层 × 3 个 TIP 盒
        s1_loading_buffer_warehouse: 6,
        s2_tip_placeholder_warehouse: 6,
        # 烧杯堆栈：3 层 × 6 列 × (样品瓶 + 烧杯)
        s3_unused_beaker_warehouse: 36,
        s3_unused_sample_vial_warehouse: 36,
        powder_container_placeholder_warehouse: 6,
        s10_liquid_reagent_placeholder_warehouse: 20,
        s11_used_beaker_warehouse: 36,
        s11_used_sample_vial_warehouse: 36,
    }
    for factory, expected in warehouses.items():
        warehouse = factory(factory.__name__)
        assert warehouse.num_items == expected
        assert len(warehouse.sites) == expected
        assert len(warehouse._ordering) == expected


def test_deck_contains_all_warehouses() -> None:
    deck = SZLabPolyStudioDeck()
    assert len(deck.children) == 6
    assert sum(warehouse.num_items for warehouse in deck.warehouses.values()) == 110
    assert set(deck.warehouses) == {
        "S1上料过渡仓",
        "S2枪头仓占位",
        "S3未使用烧杯仓",
        "S10液体试剂瓶仓占位",
        "S11使用烧杯成品仓",
        "固体粉桶仓占位",
    }


def test_physical_warehouse_factories_match_deployment_graph() -> None:
    """Python Warehouse 是启动图 Site 几何的可执行定义，二者不得漂移。"""

    graph_path = Path(__file__).resolve().parents[1] / "deployment/graphs/szlab-local-debug.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_nodes = {node["id"]: node for node in graph["nodes"]}
    factories = {
        "s1_loading_buffer": s1_loading_buffer_warehouse,
        "s2_tip_warehouse": s2_tip_placeholder_warehouse,
        "s3_unused_beaker": s3_unused_beaker_warehouse,
        "powder_container_warehouse": powder_container_placeholder_warehouse,
        "s10_liquid_reagent": s10_liquid_reagent_placeholder_warehouse,
        "s11_used_beaker": s11_used_beaker_warehouse,
    }

    for node_id, factory in factories.items():
        warehouse = factory(node_id)
        config = graph_nodes[node_id]["config"]
        assert (warehouse.get_size_x(), warehouse.get_size_y(), warehouse.get_size_z()) == (
            config["size_x"],
            config["size_y"],
            config["size_z"],
        )
        assert list(warehouse._ordering) == [site["label"] for site in config["sites"]]

        for site_config in config["sites"]:
            site = warehouse._ordering[site_config["label"]]
            position = site_config["position"]
            size = site_config["size"]
            assert (site.location.x, site.location.y, site.location.z) == (
                position["x"],
                position["y"],
                position["z"],
            )
            assert (site.get_size_x(), site.get_size_y(), site.get_size_z()) == (
                size["width"],
                size["height"],
                size["depth"],
            )


def test_s2_tip_stack_uses_confirmed_three_by_two_site_order() -> None:
    warehouse = s2_tip_placeholder_warehouse("s2")

    assert list(warehouse._ordering) == ["T11", "T12", "T21", "T22", "T31", "T32"]
    assert (warehouse.num_items_x, warehouse.num_items_y, warehouse.num_items_z) == (2, 1, 3)
    assert warehouse._ordering["T22"].location.x == 172.0
    assert warehouse._ordering["T22"].location.z == 320.0


def test_material_factories_use_mm_and_microlitre_conventions() -> None:
    materials = [
        beaker_500ml(),
        sample_vial_250ml(),
        sample_vial_500ml(),
        liquid_reagent_bottle_100ml(),
        powder_container(),
        pipette_tip(),
    ]
    assert all(item.get_size_x() > 0 and item.get_size_y() > 0 and item.get_size_z() > 0 for item in materials)
    assert beaker_500ml().max_volume == 500_000.0
    assert sample_vial_250ml().max_volume == 250_000.0
    assert sample_vial_500ml().max_volume == 500_000.0
    assert liquid_reagent_bottle_100ml().max_volume == 100_000.0
