"""SZLab S2 TIP 盒堆栈载架。"""

from __future__ import annotations

from typing import Dict, Union

from pylabrobot.resources import ResourceHolder, create_ordered_items_2d
from unilabos.resources.itemized_carrier import BottleCarrier, ResourcePLR

from szlab_poly_studio.resources.materials import tip_box


def SZLab_TipBoxStackCarrier(
    name: str,
    *,
    fill_placeholders: bool = True,
) -> BottleCarrier:
    """创建 S2 三层、每层两个 TIP 盒位的物理载架。"""

    carrier_size_x = 310.0
    carrier_size_y = 140.0
    carrier_size_z = 558.0

    num_cols = 2
    num_layers = 3
    first_slot_x = 52.0
    first_slot_y = 6.0
    first_slot_z = 120.0
    col_dx = 120.0
    layer_dz = 200.0
    slot_size_x = 86.0
    slot_size_y = 128.0
    slot_size_z = 136.0

    sites: Dict[Union[int, str], ResourcePLR] = {}
    ordering: list[str] = []
    for layer in range(num_layers):
        layer_sites = create_ordered_items_2d(
            klass=ResourceHolder,
            num_items_x=num_cols,
            num_items_y=1,
            dx=first_slot_x,
            dy=first_slot_y,
            dz=first_slot_z + layer * layer_dz,
            item_dx=col_dx,
            item_dy=0.0,
            size_x=slot_size_x,
            size_y=slot_size_y,
            size_z=slot_size_z,
        )
        for col, (_plr_key, holder) in enumerate(layer_sites.items()):
            label = f"T{layer + 1}{col + 1}"
            holder.name = f"{name}_{label}"
            sites[label] = holder
            ordering.append(label)

    carrier = BottleCarrier(
        name=name,
        size_x=carrier_size_x,
        size_y=carrier_size_y,
        size_z=carrier_size_z,
        sites=sites,
        model="SZLab_TipBoxStackCarrier",
    )
    carrier.num_items_x = num_cols
    carrier.num_items_y = 1
    carrier.num_items_z = num_layers

    if fill_placeholders:
        for label in ordering:
            carrier[label] = tip_box(name=f"{name}_tipbox_{label}")

    return carrier
