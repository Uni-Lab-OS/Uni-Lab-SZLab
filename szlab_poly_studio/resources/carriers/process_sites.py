"""Fixed process-device carriers used as Inventory Site owners.

The device remains the actuator.  These lightweight carriers only own the
physical places where a transported resource can be mounted.  Keeping them as
normal resources lets robot actions and ``host.transfer_resource`` share the
same ``ResourceSlot + site`` address.
"""

from __future__ import annotations

from collections.abc import Iterable

from pylabrobot.resources import Coordinate, ResourceHolder
from unilabos.resources.itemized_carrier import BottleCarrier

SiteGeometry = tuple[str, float, float, float, float, float, float]


def _fixed_site_carrier(
    name: str,
    *,
    size: tuple[float, float, float],
    sites: Iterable[SiteGeometry],
    category: str,
    model: str,
) -> BottleCarrier:
    holders: dict[str, ResourceHolder] = {}
    for label, x, y, z, width, height, depth in sites:
        holder = ResourceHolder(
            name=f"{name}_{label}",
            size_x=width,
            size_y=height,
            size_z=depth,
        )
        holder.location = Coordinate(x=x, y=y, z=z)
        holders[label] = holder

    carrier = BottleCarrier(
        name=name,
        size_x=size[0],
        size_y=size[1],
        size_z=size[2],
        sites=holders,
        category=category,
        model=model,
    )
    carrier.num_items_x = len(holders)
    carrier.num_items_y = 1
    carrier.num_items_z = 1
    return carrier


# One individual stirrer module: CAD bbox in its own lower-left-bottom frame.
S04_MODULE_SIZE = (215.6, 359.0, 122.1)
# Seat / model center: exact envelope X center; Y keeps the hot-plate (+≈50 mm
# from geometric Y). Beaker seat sits on the plate at z=121, Ø88.
S04_MODULE_MODEL_CENTER_XY = (S04_MODULE_SIZE[0] / 2.0, 226.618)
# Beaker seat sits 121 mm above the model bottom, Ø88.
S04_MODULE_SEAT_DIAMETER = 88.0
S04_MODULE_SEAT_Z = 121.0


def SZLab_S04ModuleCarrier(name: str, number: int) -> BottleCarrier:
    """One beaker seat owned by a single magnetic-stirrer module.

    The seat is centred on the module's hot plate at the envelope X center
    (size_x/2) and +≈50 mm in Y from geometric center, at z=121. Coordinates
    are relative to the module's own lower-left-bottom corner, so the rack
    never owns these sites.
    """

    if number not in range(1, 7):
        raise ValueError(f"S04 模块编号必须在 1-6 范围内，收到: {number}")
    center_x, center_y = S04_MODULE_MODEL_CENTER_XY
    radius = S04_MODULE_SEAT_DIAMETER / 2.0
    return _fixed_site_carrier(
        name,
        size=S04_MODULE_SIZE,
        sites=(
            (
                f"S04{number}",
                center_x - radius,
                center_y - radius,
                S04_MODULE_SEAT_Z,
                S04_MODULE_SEAT_DIAMETER,
                S04_MODULE_SEAT_DIAMETER,
                120.0,
            ),
        ),
        category="s04_process_warehouse",
        model="SZLab_S04ModuleCarrier",
    )


def SZLab_S05ProcessCarrier(name: str) -> BottleCarrier:
    """S05 camera turntable's single robot hand-off position."""

    return _fixed_site_carrier(
        name,
        size=(340.0, 329.0, 510.0),
        sites=(("S051", 127.0, 84.5, 162.0, 86.0, 86.0, 120.0),),
        category="s05_process_warehouse",
        model="SZLab_S05ProcessCarrier",
    )


# S09 pipetting station deck (plate LL origin). Tip-box seats are rectangles;
# reagent / beaker seats are circles (Inventory stores their lower-left boxes).
S09_STATION_SIZE = (800.0, 470.0, 650.0)
S09_TIP_BOX_SIZE = (86.0, 127.0, 136.0)
S09_TIP_BOX_ORIGINS = (
    (127.0, 106.0, 85.0),
    (247.0, 106.0, 85.0),
)
S09_REAGENT_DIAMETER = 57.0
S09_REAGENT_FIRST_CENTER = (140.0, 40.0, 63.0)
S09_REAGENT_PITCH_X = 95.0
S09_REAGENT_COUNT = 5
S09_BEAKER_DIAMETER = 87.0
S09_BEAKER_CENTER = (662.0, 244.0, 105.0)


def SZLab_S09ProcessCarrier(name: str) -> BottleCarrier:
    """S09 pipetting-station sites owned by the device-mounted warehouse.

    Layout relative to the station plate lower-left-bottom:
    - TIP1/TIP2: tip-box rectangles 86×127 at LL (127,106,85) / (247,106,85)
    - REAGENT1..5: Ø57 circles, first center (140,40,63), Δx=+95
    - BEAKER1: Ø87 circle centered at (662,244,105)
    """

    tip_sites = tuple(
        (
            f"TIP{index}",
            origin[0],
            origin[1],
            origin[2],
            S09_TIP_BOX_SIZE[0],
            S09_TIP_BOX_SIZE[1],
            S09_TIP_BOX_SIZE[2],
        )
        for index, origin in enumerate(S09_TIP_BOX_ORIGINS, start=1)
    )
    reagent_radius = S09_REAGENT_DIAMETER / 2.0
    reagent_sites = tuple(
        (
            f"REAGENT{index}",
            S09_REAGENT_FIRST_CENTER[0]
            + (index - 1) * S09_REAGENT_PITCH_X
            - reagent_radius,
            S09_REAGENT_FIRST_CENTER[1] - reagent_radius,
            S09_REAGENT_FIRST_CENTER[2],
            S09_REAGENT_DIAMETER,
            S09_REAGENT_DIAMETER,
            105.0,
        )
        for index in range(1, S09_REAGENT_COUNT + 1)
    )
    beaker_radius = S09_BEAKER_DIAMETER / 2.0
    beaker_site = (
        (
            "BEAKER1",
            S09_BEAKER_CENTER[0] - beaker_radius,
            S09_BEAKER_CENTER[1] - beaker_radius,
            S09_BEAKER_CENTER[2],
            S09_BEAKER_DIAMETER,
            S09_BEAKER_DIAMETER,
            120.0,
        ),
    )
    return _fixed_site_carrier(
        name,
        size=S09_STATION_SIZE,
        sites=tip_sites + reagent_sites + beaker_site,
        category="s09_process_warehouse",
        model="SZLab_S09ProcessCarrier",
    )


def SZLab_S06ProcessCarrier(name: str) -> BottleCarrier:
    """S06 solvent-addition platform's single beaker position."""

    return _fixed_site_carrier(
        name,
        size=(285.0, 205.0, 727.0),
        sites=(("S061", 101.5, 54.0, 303.0, 86.0, 86.0, 120.0),),
        category="s06_process_warehouse",
        model="SZLab_S06ProcessCarrier",
    )


def SZLab_S07ProcessCarrier(name: str) -> BottleCarrier:
    """S07 powder carousel plus the two existing S072 robot hand-off sites.

    P01..P10 are Inventory authority for powder cartridges and are not direct
    robot targets. S0721/S0722 map the existing PLC robot product hand-off
    program; their geometry remains an installation estimate until surveyed.
    """

    centers = (
        (416.0, 251.0),
        (380.668, 359.74),
        (288.168, 426.946),
        (173.832, 426.946),
        (81.332, 359.74),
        (46.0, 251.0),
        (81.332, 142.26),
        (173.832, 75.054),
        (288.168, 75.054),
        (380.668, 142.26),
    )
    sites = tuple(
        (
            f"P{number:02d}",
            center_x - 35.0,
            center_y - 35.0,
            379.5,
            70.0,
            70.0,
            190.0,
        )
        for number, (center_x, center_y) in enumerate(centers, start=1)
    ) + (
        ("S0721", 500.0, 95.0, 352.0, 86.0, 86.0, 120.0),
        ("S0722", 500.0, 315.0, 352.0, 86.0, 86.0, 120.0),
    )
    return _fixed_site_carrier(
        name,
        size=(770.0, 503.0, 654.5),
        sites=sites,
        category="s07_process_warehouse",
        model="SZLab_S07ProcessCarrier",
    )
