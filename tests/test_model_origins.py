"""Regression checks for the model-owned SZLab 3D coordinate contract.

PLR placements use millimetres from a resource's lower-left-bottom corner. The
frontend remains model-agnostic, so each Xacro maps that origin to its CAD
geometry itself.
"""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier
from szlab_poly_studio.resources.carriers.powder import SZLab_PowderContainerStackCarrier
from szlab_poly_studio.resources.carriers.reagent import SZLab_ReagentBottleStackCarrier

PACKAGE = Path(__file__).parents[1] / "szlab_poly_studio"

# Translation/rotation on the fixed joint immediately below the public macro
# root. Values are metres/radians. Container translations put the vessel axis
# at half its PLR footprint; CAD translations cancel the measured bbox minimum.
EXPECTED_ROOTS = {
    "devices/szlab_mixer_photoshotting/models/device.xacro": (
        (0.293683, 0.200149, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_mixer_pipetting_station/models/device.xacro": (
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_mixer_pump/models/device.xacro": (
        (0.1425, 0.103, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_mixer_robot/models/device.xacro": (
        (0.0, 0.08, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_mixer_stirrer/models/device.xacro": (
        (0.33391374, 0.17660786, -0.008),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_mixer_stirrer_warehouse/models/resource.xacro": (
        (0.355, 0.164991, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_s07_solid_addition/models/device.xacro": (
        (0.38575, 0.2515, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "devices/szlab_s08_cap_station/models/device.xacro": (
        (0.0545, 0.18, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_beaker_500ml/models/resource.xacro": (
        (0.043, 0.043, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_liquid_reagent_bottle_100ml/models/resource.xacro": (
        (0.028, 0.028, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_poly_beaker_warehouse/models/resource.xacro": (
        (0.394994, 0.1, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_poly_powder_container_placeholder_warehouse/models/resource.xacro": (
        (0.05, 0.185014, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_poly_s10_liquid_reagent_placeholder_warehouse/models/resource.xacro": (
        (0.279986, 0.06, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_poly_s1_loading_buffer_warehouse/models/resource.xacro": (
        (0.100083, 0.22108, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_poly_s2_tip_placeholder_warehouse/models/resource.xacro": (
        (0.155012, 0.07, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_powder_container/models/resource.xacro": (
        (0.035, 0.035, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_sample_vial_500ml/models/resource.xacro": (
        (0.043, 0.043, 0.0),
        (0.0, 0.0, 0.0),
    ),
    "resources/szlab_tip_box/models/resource.xacro": (
        (0.043, 0.06403, 0.0),
        (0.0, 0.0, 0.0),
    ),
}


def _model_root(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
    root = ET.parse(path).getroot()
    joint = next(
        joint
        for joint in root.iter("joint")
        if joint.attrib["name"].endswith(("device_link_joint", "base_joint"))
    )
    origin = joint.find("origin")
    assert origin is not None
    return (
        tuple(float(value) for value in origin.attrib["xyz"].split()),
        tuple(float(value) for value in origin.attrib["rpy"].split()),
    )


@pytest.mark.parametrize("relative_path", EXPECTED_ROOTS)
def test_each_xacro_owns_its_lower_left_origin(relative_path: str) -> None:
    translation, rotation = _model_root(PACKAGE / relative_path)
    expected_translation, expected_rotation = EXPECTED_ROOTS[relative_path]
    assert translation == pytest.approx(expected_translation)
    assert rotation == pytest.approx(expected_rotation)


def test_all_top_level_xacros_are_covered_by_the_origin_contract() -> None:
    actual = {
        path.relative_to(PACKAGE).as_posix()
        for pattern in ("**/models/device.xacro", "**/models/resource.xacro")
        for path in PACKAGE.glob(pattern)
    }
    assert actual == set(EXPECTED_ROOTS)


@pytest.mark.parametrize(
    ("carrier", "site_name", "model_path", "expected_center_mm"),
    [
        (
            SZLab_BeakerStackCarrier("beakers", fill_placeholders=False),
            "L1B1",
            "resources/szlab_beaker_500ml/models/resource.xacro",
            (95.0, 150.0),
        ),
        (
            SZLab_BeakerStackCarrier("samples", fill_placeholders=False),
            "L1A1",
            "resources/szlab_sample_vial_500ml/models/resource.xacro",
            (95.0, 50.0),
        ),
        (
            SZLab_ReagentBottleStackCarrier("reagents", fill_placeholders=False),
            "R1C1",
            "resources/szlab_liquid_reagent_bottle_100ml/models/resource.xacro",
            (80.0, 50.0),
        ),
        (
            SZLab_PowderContainerStackCarrier("powders", fill_placeholders=False),
            "L1C1",
            "resources/szlab_powder_container/models/resource.xacro",
            (50.0, 85.0),
        ),
    ],
)
def test_container_model_axis_lands_on_carrier_hole_center(
    carrier, site_name: str, model_path: str, expected_center_mm: tuple[float, float]
) -> None:
    site = carrier[site_name]
    translation, _rotation = _model_root(PACKAGE / model_path)
    rendered_axis_mm = (
        site.location.x + translation[0] * 1000.0,
        site.location.y + translation[1] * 1000.0,
    )
    assert rendered_axis_mm == pytest.approx(expected_center_mm)


def test_xacro_declarations_need_no_renderer_position_or_rotation_overrides() -> None:
    declarations = [
        *PACKAGE.glob("devices/*/device.py"),
        *PACKAGE.glob("resources/*.py"),
    ]
    for path in declarations:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                model_keyword = next(
                    (
                        keyword
                        for keyword in decorator.keywords
                        if keyword.arg == "model"
                    ),
                    None,
                )
                if model_keyword is None:
                    continue
                model = ast.literal_eval(model_keyword.value)
                if model.get("format") != "xacro":
                    continue
                assert "position" not in model, f"{path}: model position belongs in Xacro"
                assert "rotation" not in model, f"{path}: model rotation belongs in Xacro"
