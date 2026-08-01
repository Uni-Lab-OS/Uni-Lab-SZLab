from __future__ import annotations

import json
from typing import Any

from szlab_poly_studio.devices.szlab_s07_solid_addition.device import SZLabS07SolidAdditionDevice
from szlab_poly_studio.devices.szlab_s07_solid_addition.sensors import (
    NODE_PARAMS_WRITTEN,
    NODE_PROCESS_SELECT,
    PROCESS_SCAN_CARTRIDGES,
)


def test_load_powder_params_from_json(tmp_path) -> None:
    params_path = tmp_path / "powder-params.json"
    params_path.write_text(
        json.dumps(
            {
                "test-recipe": {
                    "coarse_params": {"shake_max_speed": 800},
                    "fine_params": {"shake_max_speed": 600},
                }
            }
        ),
        encoding="utf-8",
    )
    device = object.__new__(SZLabS07SolidAdditionDevice)

    coarse, fine = device._load_powder_params_from_json(str(params_path), "test-recipe")

    assert coarse == {"shake_max_speed": 800}
    assert fine == {"shake_max_speed": 600}


def test_scan_reset_only_writes_shared_control_variables() -> None:
    writes: list[tuple[str, Any]] = []

    class FakeGateway:
        def write_variable(self, name: str, value: Any) -> None:
            writes.append((name, value))

    device = object.__new__(SZLabS07SolidAdditionDevice)
    device._plc_gateway = FakeGateway()

    device._reset_unilab_written_params(PROCESS_SCAN_CARTRIDGES)

    assert writes == [
        (NODE_PROCESS_SELECT, 0),
        (NODE_PARAMS_WRITTEN, False),
    ]
