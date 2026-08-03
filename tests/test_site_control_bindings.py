from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from szlab_poly_studio.common.site_control_bindings import (
    S1_INVENTORY_ONLY_SITE_LABELS,
    iter_robot_site_bindings,
    resolve_s071_site,
    resolve_s2_site,
    resolve_s3_site,
    resolve_s10_site,
    resolve_s11_site,
)


def test_every_physical_warehouse_site_is_classified() -> None:
    graph_path = Path(__file__).resolve().parents[1] / "deployment/graphs/szlab-local-debug.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    physical_warehouses = {
        "s1_loading_buffer",
        "s2_tip_warehouse",
        "s3_unused_beaker",
        "powder_container_warehouse",
        "s10_liquid_reagent",
        "s11_used_beaker",
    }
    graph_sites = {
        (node["id"], site["label"])
        for node in graph["nodes"]
        if node["id"] in physical_warehouses
        for site in node["config"]["sites"]
    }

    bindings = list(iter_robot_site_bindings())
    classified_sites = {
        ("s1_loading_buffer", label) for label in S1_INVENTORY_ONLY_SITE_LABELS
    } | {(binding.warehouse_instance_id, binding.site_label) for binding in bindings}

    assert len(graph_sites) == 110
    assert len(bindings) == 104
    assert graph_sites == classified_sites
    assert Counter(binding.warehouse_instance_id for binding in bindings) == {
        "s2_tip_warehouse": 6,
        "s3_unused_beaker": 36,
        "powder_container_warehouse": 6,
        "s10_liquid_reagent": 20,
        "s11_used_beaker": 36,
    }
    assert len({binding.presence_variable for binding in bindings}) == 104


@pytest.mark.parametrize("position", [4, "4", "2-2", "T22"])
def test_s2_accepts_controller_grid_and_site_expressions(position: int | str) -> None:
    binding = resolve_s2_site(position)

    assert binding.site_label == "T22"
    assert binding.controller_position == 4
    assert binding.presence_variable == "传感器状态_上位机[0].NO[3]"


@pytest.mark.parametrize("position", [4, "4", "2-1", "L2C1"])
def test_s071_second_layer_is_compact_controller_position_four(position: int | str) -> None:
    binding = resolve_s071_site(position)

    assert binding.site_label == "L2C1"
    assert binding.controller_position == 4
    assert binding.presence_variable == "传感器状态_上位机[3].NO[11]"


def test_s3_and_s11_bind_product_type_to_physical_ab_row() -> None:
    s3_sample = resolve_s3_site(3, "L2A1")
    s3_beaker = resolve_s3_site(1, "L2B1")
    s11_sample = resolve_s11_site(3, 7)

    assert (s3_sample.site_label, s3_sample.controller_position) == ("L2A1", 7)
    assert (s3_beaker.site_label, s3_beaker.controller_position) == ("L2B1", 7)
    assert (s11_sample.site_label, s11_sample.controller_position) == ("L2A1", 7)
    with pytest.raises(ValueError, match="产品类型"):
        resolve_s3_site(2, "2-1")
    with pytest.raises(ValueError, match="A/B 行"):
        resolve_s11_site(3, "L2B1")


@pytest.mark.parametrize("position", [20, "20", "4-5", "R4C5"])
def test_s10_accepts_controller_grid_and_site_expressions(position: int | str) -> None:
    binding = resolve_s10_site(position)

    assert binding.site_label == "R4C5"
    assert binding.controller_position == 20
    assert binding.presence_variable == "传感器状态_上位机[5].NO[15]"
