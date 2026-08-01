"""SZLab S1 上料过渡仓（tip 盒上料工装）载架 — 写法对齐 bottle_carriers。

外框与位点取自 CAD（DXY260502-13.03-00 tip盒上料工装）：模型本体
441.9 × 200 × 402.8，两层托板顶面 z=70 / 260，每层 3 个 86 × 128 的 tip 盒位，
盒位中心沿长边 101 / 221 / 341（间距 120）。

台面上这台工装转了 90°，长边沿 Y 摆，因此这里的位点已经换算成台面朝向：
占位 200 (X) × 442 (Y)，盒位 128 (X) × 86 (Y)，靠台面一侧（X 小的一侧）。
"""

from __future__ import annotations

from typing import Dict, Union

from pylabrobot.resources import ResourceHolder, create_ordered_items_2d
from unilabos.resources.itemized_carrier import BottleCarrier, ResourcePLR

from szlab_poly_studio.resources.materials import tip_box


def SZLab_TipBoxLoaderCarrier(
    name: str,
    *,
    fill_placeholders: bool = True,
) -> BottleCarrier:
    """SZLab tip 盒上料工装 - 2 层 × 3 位

    参数:
    - name: 载架名称前缀
    - fill_placeholders: 是否在每个位点放入占位 TIP 盒

    说明:
    - 载架尺寸 W200 × L442 × H403（长边沿 Y，已按台面转 90° 换算）
    - 托板顶面 z=70 / 260，盒位中心 y=101/221/341，x=70
    - 标签 L{层}C{列}
    """

    # 载架尺寸 (mm)
    carrier_size_x = 200.0
    carrier_size_y = 442.0
    carrier_size_z = 403.0

    num_cols = 3
    num_layers = 2
    first_center_x = 70.0
    first_center_y = 101.0
    first_seat_z = 70.0
    col_dy = 120.0
    layer_dz = 190.0

    # TIP 盒转 90° 后的占位
    slot_size_x = 128.0
    slot_size_y = 86.0
    slot_size_z = 136.0

    start_x = first_center_x - slot_size_x / 2.0
    start_y = first_center_y - slot_size_y / 2.0

    sites: Dict[Union[int, str], ResourcePLR] = {}
    ordering: list[str] = []

    for layer in range(num_layers):
        layer_sites = create_ordered_items_2d(
            klass=ResourceHolder,
            num_items_x=1,
            num_items_y=num_cols,
            dx=start_x,
            dy=start_y,
            dz=first_seat_z + layer * layer_dz,
            item_dx=0.0,
            item_dy=col_dy,
            size_x=slot_size_x,
            size_y=slot_size_y,
            size_z=slot_size_z,
        )
        # PLR 的字母行从高 y 排起，这里按 y 递增编号，C1 = 最靠近原点的盒位
        for col, (_plr_key, holder) in enumerate(
            reversed(list(layer_sites.items()))
        ):
            label = f"L{layer + 1}C{col + 1}"
            holder.name = f"{name}_{label}"
            sites[label] = holder
            ordering.append(label)

    carrier = BottleCarrier(
        name=name,
        size_x=carrier_size_x,
        size_y=carrier_size_y,
        size_z=carrier_size_z,
        sites=sites,
        model="SZLab_TipBoxLoaderCarrier",
    )
    carrier.num_items_x = 1
    carrier.num_items_y = num_cols
    carrier.num_items_z = num_layers

    if fill_placeholders:
        for label in ordering:
            carrier[label] = tip_box(name=f"{name}_tipbox_{label}")

    return carrier
