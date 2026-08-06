"""Map legacy submit_* station/task calls onto MoveIt simulation site keys.

Workflow entry points stay unchanged (``submit_place_to_s06``, …). Under
``moveit_sim`` the device resolves those calls to canonical
``<warehouse>/<site>`` strings that must exist in
``standard_moveit_site_targets``. Missing mappings fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


GateKind = Literal["pick", "place"]


@dataclass(frozen=True)
class MoveItSimulationSiteTarget:
    target_site: str
    payload_profile: str
    fixture_id: str


def resolve_legacy_moveit_site(
    *,
    station: str,
    task: str,
    position: Any = None,
    product_type: Any = None,
) -> MoveItSimulationSiteTarget:
    """Resolve one legacy PLC station action to a MoveIt simulation site.

    First batch covers the liquid-stirring demo (S06 place/pick, S04 place/pick).
    Other stations raise ``ValueError`` until site_targets and mappings exist.
    """

    station_key = str(station).strip().upper()
    task_key = str(task).strip().lower()
    if task_key not in {"pick", "place"}:
        raise ValueError(f"MoveIt 仿真不支持 legacy 任务类型: {task}")

    if station_key == "S06":
        target_site = "s06_process_warehouse/S061"
        payload_profile = "beaker_500ml@v1"
        fixture_id = f"legacy-s06-{task_key}"
        return MoveItSimulationSiteTarget(target_site, payload_profile, fixture_id)

    if station_key == "S04":
        slot = _s04_position(position)
        target_site = f"{s04_warehouse_id(slot)}/S04{slot}"
        payload_profile = "beaker_500ml@v1"
        fixture_id = f"legacy-s04-{task_key}-p{slot}"
        return MoveItSimulationSiteTarget(target_site, payload_profile, fixture_id)

    raise ValueError(
        f"MoveIt 仿真尚未映射 legacy 工位 {station_key}/{task_key}；"
        "请在 legacy_to_moveit_sites 与 standard_moveit_site_targets 中补齐"
    )


def s04_warehouse_id(slot: int) -> str:
    """Each stirrer module owns its own single-seat warehouse.

    Module 1 keeps the historical ``s04_process_warehouse`` id so existing
    workflows addressing ``s04_process_warehouse/S041`` keep resolving.
    """

    return "s04_process_warehouse" if slot == 1 else f"s04_process_warehouse_{slot}"


def _s04_position(position: Any) -> int:
    if position is None:
        raise ValueError("S04 MoveIt 仿真需要 position（1-6）")
    value = int(position)
    if value not in range(1, 7):
        raise ValueError(f"S04 位置必须在 1-6 范围内，收到: {position}")
    return value
