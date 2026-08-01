from unilabos.registry.decorators import resource
from unilabos.resources.warehouse import WareHouse, warehouse_factory


@resource(
    id="szlab_poly_s1_loading_buffer_warehouse",
    category=["szlab_poly_studio", "warehouse", "tip_stack"],
    description="苏州实验室 S1 上料过渡仓：tip 盒上料工装，2层×3个TIP盒（CAD DXY260502-13.03-00）",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s1_loading_buffer_warehouse/models/shape.yml",
        },
    },
)
def s1_loading_buffer_warehouse(name: str = "S1上料过渡仓"):
    from szlab_poly_studio.resources.carriers.tip_box_loader import SZLab_TipBoxLoaderCarrier

    return SZLab_TipBoxLoaderCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s3_unused_beaker_warehouse",
    category=["szlab_poly_studio", "warehouse", "beaker_stack"],
    description="苏州实验室烧杯堆栈2：3层×6列，A行500mL样品瓶 / B行烧杯",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s3_unused_beaker_warehouse/models/shape.yml",
        },
    },
)
def s3_unused_beaker_warehouse(name: str = "烧杯堆栈2"):
    from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier

    return SZLab_BeakerStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s11_used_beaker_warehouse",
    category=["szlab_poly_studio", "warehouse", "beaker_stack"],
    description="苏州实验室烧杯堆栈1：3层×6列，A行500mL样品瓶 / B行烧杯",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s11_used_beaker_warehouse/models/shape.yml",
        },
    },
)
def s11_used_beaker_warehouse(name: str = "烧杯堆栈1"):
    from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier

    return SZLab_BeakerStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s2_tip_placeholder_warehouse",
    category=["szlab_poly_studio", "warehouse"],
    description="苏州实验室 S2 枪头仓占位，6位",
)
def s2_tip_placeholder_warehouse(name: str = "S2枪头仓占位") -> WareHouse:
    return warehouse_factory(
        name=name,
        num_items_x=6,
        num_items_y=1,
        num_items_z=1,
        dx=10.0,
        dy=10.0,
        dz=10.0,
        item_dx=60.0,
        item_dy=80.0,
        item_dz=120.0,
        layout="row-major",
        category="warehouse",
    )


@resource(
    id="szlab_poly_powder_container_placeholder_warehouse",
    category=["szlab_poly_studio", "warehouse", "powder_stack"],
    description="苏州实验室固体粉桶堆栈：2层×3位，落座面 z=220/530（CAD DXY260502-05-00）",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_powder_container_placeholder_warehouse/models/shape.yml",
        },
    },
)
def powder_container_placeholder_warehouse(name: str = "固体粉桶仓占位"):
    from szlab_poly_studio.resources.carriers.powder import (
        SZLab_PowderContainerStackCarrier,
    )

    return SZLab_PowderContainerStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s10_liquid_reagent_placeholder_warehouse",
    category=["szlab_poly_studio", "warehouse", "reagent_stack"],
    description="苏州实验室试剂瓶堆栈：4层×5列，Ø56（bottle_carriers 风格）",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s10_liquid_reagent_placeholder_warehouse/models/shape.yml",
        },
    },
)
def s10_liquid_reagent_placeholder_warehouse(name: str = "试剂瓶堆栈"):
    from szlab_poly_studio.resources.carriers.reagent import SZLab_ReagentBottleStackCarrier

    return SZLab_ReagentBottleStackCarrier(name, fill_placeholders=False)
