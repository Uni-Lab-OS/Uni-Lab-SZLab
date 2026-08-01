"""SZLab 烧杯堆栈载架 — 写法对齐 Uni-Lab-OS bioyond bottle_carriers。

坐标约定：相对载架左下角 (mm)。
每层 6 列 × 2 行：
  - A 行（低 y）：500 mL 样品瓶，圆心相对 slot 左下角 (+50, +50)
  - B 行（高 y）：500 mL 烧杯，圆心相对 slot 左下角 (+50, +150)
共 3 层，层间高度差 240 mm；首层 z=80。

注意：pylabrobot create_ordered_items_2d 的字母行与 y 相反——
PLR「A」在高 y、「B」在低 y。下方按几何赋值，再用用户语义标签 L{层}A/B{列}。
"""

from __future__ import annotations

from typing import Dict, Union

from pylabrobot.resources import ResourceHolder, create_ordered_items_2d
from unilabos.resources.itemized_carrier import BottleCarrier, ResourcePLR

from szlab_poly_studio.resources.materials import beaker_500ml, sample_vial_500ml


def SZLab_BeakerStackCarrier(
    name: str,
    *,
    fill_placeholders: bool = True,
) -> BottleCarrier:
    """SZLab 烧杯堆栈 - 3 层 × (6 列 × 2 行物料位)

    参数:
    - name: 载架名称前缀
    - fill_placeholders: 是否放入占位样品瓶/烧杯

    说明:
    - 载架尺寸 L790 × W200 × H560
    - slot 网格：首 slot 左下角 (45, 0, 80)，同行 Δx=120，层间 Δz=240
    - A 行（低 y）：500 mL 样品瓶；B 行（高 y）：500 mL 烧杯
    """

    # 载架尺寸 (mm)
    carrier_size_x = 790.0
    carrier_size_y = 200.0
    carrier_size_z = 560.0

    num_cols = 6
    num_layers = 3
    first_slot_x = 45.0
    first_slot_y = 0.0
    first_slot_z = 80.0
    col_dx = 120.0
    layer_spacing_z = 240.0

    # 每个 slot 内两种物料的圆心（相对 slot 左下角）
    sample_center_x = 50.0
    sample_center_y = 50.0
    beaker_center_y = 150.0

    # holder 边长取样品瓶 Ø86（烧杯 Ø90，圆心仍按 +50/+150）
    bottle_diameter = 86.0
    bottle_spacing_y = beaker_center_y - sample_center_y  # 100

    start_x = first_slot_x + sample_center_x - bottle_diameter / 2.0
    start_y = first_slot_y + sample_center_y - bottle_diameter / 2.0

    sites: Dict[Union[int, str], ResourcePLR] = {}
    ordering: list[str] = []

    for layer in range(num_layers):
        layer_sites = create_ordered_items_2d(
            klass=ResourceHolder,
            num_items_x=num_cols,
            num_items_y=2,
            dx=start_x,
            dy=start_y,
            dz=first_slot_z + layer * layer_spacing_z,
            item_dx=col_dx,
            item_dy=bottle_spacing_y,
            size_x=bottle_diameter,
            size_y=bottle_diameter,
            size_z=bottle_diameter,
        )
        # PLR A=高y→用户 B 烧杯；PLR B=低y→用户 A 样品瓶
        for col in range(num_cols):
            for plr_row in range(2):
                idx = col * 2 + plr_row
                plr_key = list(layer_sites.keys())[idx]
                holder = layer_sites[plr_key]
                if plr_row == 0:
                    label = f"L{layer + 1}B{col + 1}"
                else:
                    label = f"L{layer + 1}A{col + 1}"
                holder.name = f"{name}_{label}"
                sites[label] = holder
                ordering.append(label)

    carrier = BottleCarrier(
        name=name,
        size_x=carrier_size_x,
        size_y=carrier_size_y,
        size_z=carrier_size_z,
        sites=sites,
        model="SZLab_BeakerStackCarrier",
    )
    carrier.num_items_x = num_cols
    carrier.num_items_y = 2
    carrier.num_items_z = num_layers

    if fill_placeholders:
        for label in ordering:
            layer_ch = label[1]
            row_ch = label[2]
            col_ch = label[3:]
            if row_ch == "A":
                carrier[label] = sample_vial_500ml(
                    name=f"{name}_sample_L{layer_ch}C{col_ch}"
                )
            else:
                carrier[label] = beaker_500ml(
                    name=f"{name}_beaker_L{layer_ch}C{col_ch}"
                )

    return carrier
