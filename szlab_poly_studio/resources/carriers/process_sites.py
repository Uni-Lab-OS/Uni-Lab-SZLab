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


def SZLab_S04ProcessCarrier(name: str) -> BottleCarrier:
    """S04 two-level, three-column magnetic-stirring beaker mount."""

    centers_x = (135.1, 360.1, 585.1)
    sites = []
    for layer, seat_z in enumerate((150.0, 535.0), start=1):
        for column, center_x in enumerate(centers_x, start=1):
            number = (layer - 1) * 3 + column
            sites.append(
                (
                    f"S04{number}",
                    center_x - 43.0,
                    132.4 - 43.0,
                    seat_z,
                    86.0,
                    86.0,
                    120.0,
                )
            )
    return _fixed_site_carrier(
        name,
        size=(710.0, 359.0, 780.0),
        sites=sites,
        category="s04_process_warehouse",
        model="SZLab_S04ProcessCarrier",
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
