"""SZLab 工作站中可被 warehouse/site 承载的标准物料定义。"""

from __future__ import annotations

from pylabrobot.resources import Container, Resource
from unilabos.registry.decorators import resource


def _container(
    *,
    name: str,
    diameter_mm: float,
    height_mm: float,
    max_volume_ul: float,
    category: str,
) -> Container:
    return Container(
        name=name,
        size_x=diameter_mm,
        size_y=diameter_mm,
        size_z=height_mm,
        max_volume=max_volume_ul,
        category=category,
    )


@resource(
    id="szlab_beaker_500ml",
    displayname="SZLab 500 mL 烧杯",
    category=["szlab_poly_studio", "container", "beaker"],
    description="S03/S11 堆栈与 S04-S07 工艺使用的 500 mL 烧杯。",
)
def beaker_500ml(name: str = "SZLabBeaker500mL") -> Container:
    return _container(
        name=name,
        diameter_mm=90.0,
        height_mm=120.0,
        max_volume_ul=500_000.0,
        category="beaker",
    )


@resource(
    id="szlab_sample_vial_250ml",
    displayname="SZLab 250 mL 样品瓶",
    category=["szlab_poly_studio", "container", "sample_vial"],
    description="S08 开关盖与 S09 移液工艺使用的 250 mL 样品瓶。",
)
def sample_vial_250ml(name: str = "SZLabSampleVial250mL") -> Container:
    return _container(
        name=name,
        diameter_mm=66.0,
        height_mm=140.0,
        max_volume_ul=250_000.0,
        category="sample_vial",
    )


@resource(
    id="szlab_sample_vial_500ml",
    displayname="SZLab 500 mL 样品瓶",
    category=["szlab_poly_studio", "container", "sample_vial"],
    description="S08 开关盖与成品堆栈使用的 500 mL 样品瓶。",
)
def sample_vial_500ml(name: str = "SZLabSampleVial500mL") -> Container:
    return _container(
        name=name,
        diameter_mm=86.0,
        height_mm=175.0,
        max_volume_ul=500_000.0,
        category="sample_vial",
    )


@resource(
    id="szlab_liquid_reagent_bottle_100ml",
    displayname="SZLab 100 mL 液体试剂瓶",
    category=["szlab_poly_studio", "container", "liquid_reagent"],
    description="S09/S10 使用的 100 mL 液体试剂瓶。",
)
def liquid_reagent_bottle_100ml(
    name: str = "SZLabLiquidReagentBottle100mL",
) -> Container:
    return _container(
        name=name,
        diameter_mm=45.0,
        height_mm=105.0,
        max_volume_ul=100_000.0,
        category="liquid_reagent",
    )


@resource(
    id="szlab_powder_container",
    displayname="SZLab 固体粉罐",
    category=["szlab_poly_studio", "container", "powder_reagent"],
    description="S07 固体投料工位使用的二维码粉罐。",
)
def powder_container(name: str = "SZLabPowderContainer") -> Container:
    return _container(
        name=name,
        diameter_mm=78.0,
        height_mm=115.0,
        max_volume_ul=300_000.0,
        category="powder_reagent",
    )


@resource(
    id="szlab_pipette_tip",
    displayname="SZLab 移液枪头",
    category=["szlab_poly_studio", "consumable", "tip"],
    description="S02/S09 搬运和移液工艺使用的一次性枪头。",
)
def pipette_tip(name: str = "SZLabPipetteTip") -> Resource:
    return Resource(
        name=name,
        size_x=8.0,
        size_y=8.0,
        size_z=55.0,
        category="tip",
    )
