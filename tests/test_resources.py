from __future__ import annotations

from szlab_poly_studio.decks import SZLabPolyStudioDeck
from szlab_poly_studio.materials import (
    beaker_500ml,
    liquid_reagent_bottle_100ml,
    pipette_tip,
    powder_container,
    sample_vial_250ml,
    sample_vial_500ml,
)
from szlab_poly_studio.warehouses import (
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
        s1_loading_buffer_warehouse: 4,
        s2_tip_placeholder_warehouse: 6,
        s3_unused_beaker_warehouse: 18,
        s3_unused_sample_vial_warehouse: 18,
        powder_container_placeholder_warehouse: 6,
        s10_liquid_reagent_placeholder_warehouse: 20,
        s11_used_beaker_warehouse: 18,
        s11_used_sample_vial_warehouse: 18,
    }
    for factory, expected in warehouses.items():
        warehouse = factory(factory.__name__)
        assert warehouse.num_items == expected
        assert len(warehouse.sites) == expected
        assert len(warehouse._ordering) == expected


def test_deck_contains_all_eight_warehouses() -> None:
    deck = SZLabPolyStudioDeck()
    assert len(deck.children) == 8
    assert set(deck.warehouses) == {
        "S1上料过渡仓",
        "S2枪头仓占位",
        "S3未使用烧杯仓",
        "S3未使用样品瓶仓",
        "S10液体试剂瓶仓占位",
        "S11使用烧杯成品仓",
        "S11使用样品瓶成品仓",
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
