from __future__ import annotations

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
    beaker_warehouse,
    powder_container_placeholder_warehouse,
    s1_loading_buffer_warehouse,
    s2_tip_placeholder_warehouse,
    s10_liquid_reagent_placeholder_warehouse,
)


def test_warehouse_site_counts_and_keys() -> None:
    warehouses = {
        # tip 盒上料工装：2 层 × 3 个 TIP 盒
        s1_loading_buffer_warehouse: 6,
        s2_tip_placeholder_warehouse: 6,
        # 烧杯堆栈：3 层 × 6 列 × (样品瓶 + 烧杯)；S3/S11 同型
        beaker_warehouse: 36,
        powder_container_placeholder_warehouse: 6,
        s10_liquid_reagent_placeholder_warehouse: 20,
    }
    for factory, expected in warehouses.items():
        warehouse = factory(factory.__name__)
        assert warehouse.num_items == expected
        assert len(warehouse.sites) == expected
        assert len(warehouse._ordering) == expected


def test_deck_contains_all_warehouses() -> None:
    deck = SZLabPolyStudioDeck()
    assert len(deck.children) == 6
    assert set(deck.warehouses) == {
        "S1上料过渡仓",
        "S2枪头仓占位",
        "S3未使用烧杯仓",
        "S10液体试剂瓶仓占位",
        "S11使用烧杯成品仓",
        "固体粉桶仓占位",
    }


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
