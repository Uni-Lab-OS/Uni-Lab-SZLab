from unilabos.registry.decorators import resource


@resource(
    id="szlab_poly_s1_loading_buffer_warehouse",
    category=["szlab_poly_studio", "warehouse", "tip_stack"],
    description="苏州实验室 S1 上料过渡仓：tip 盒上料工装，2层×3个TIP盒（CAD DXY260502-13.03-00）",
    model={
        "format": "xacro",
        "entry": "szlab_poly_s1_loading_buffer_warehouse/models/resource.xacro",
        "macro": "szlab_poly_s1_loading_buffer_warehouse",
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
        "format": "xacro",
        "entry": "szlab_poly_beaker_warehouse/models/resource.xacro",
        "macro": "szlab_poly_beaker_warehouse",
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
    id="szlab_poly_s3_unused_sample_vial_warehouse",
    category=["szlab_poly_studio", "warehouse", "sample_vial_stack"],
    description="苏州实验室 S3 未使用样品瓶逻辑仓：与烧杯堆栈2共用物理载架的样品瓶位",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s3_unused_sample_vial_warehouse/models/shape.yml",
        },
    },
)
def s3_unused_sample_vial_warehouse(name: str = "S3未使用样品瓶仓"):
    from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier

    return SZLab_BeakerStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s11_used_beaker_warehouse",
    category=["szlab_poly_studio", "warehouse", "beaker_stack"],
    description="苏州实验室烧杯堆栈1：3层×6列，A行500mL样品瓶 / B行烧杯",
    model={
        "format": "xacro",
        "entry": "szlab_poly_beaker_warehouse/models/resource.xacro",
        "macro": "szlab_poly_beaker_warehouse",
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
    id="szlab_poly_s11_used_sample_vial_warehouse",
    category=["szlab_poly_studio", "warehouse", "sample_vial_stack"],
    description="苏州实验室 S11 使用样品瓶成品逻辑仓：与烧杯堆栈1共用物理载架的样品瓶位",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s11_used_sample_vial_warehouse/models/shape.yml",
        },
    },
)
def s11_used_sample_vial_warehouse(name: str = "S11使用样品瓶成品仓"):
    from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier

    return SZLab_BeakerStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_s2_tip_placeholder_warehouse",
    category=["szlab_poly_studio", "warehouse", "tip_stack"],
    description="苏州实验室 S2 枪头仓：3层×2个TIP盒（CAD DXY260502-02-00）",
    model={
        "format": "xacro",
        "entry": "szlab_poly_s2_tip_placeholder_warehouse/models/resource.xacro",
        "macro": "szlab_poly_s2_tip_placeholder_warehouse",
    },
)
def s2_tip_placeholder_warehouse(name: str = "S2枪头仓占位"):
    from szlab_poly_studio.resources.carriers.tip_box_stack import SZLab_TipBoxStackCarrier

    return SZLab_TipBoxStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_poly_powder_container_placeholder_warehouse",
    category=["szlab_poly_studio", "warehouse", "powder_stack"],
    description="苏州实验室固体粉桶堆栈：2层×3位，落座面 z=220/530（CAD DXY260502-05-00）",
    model={
        "format": "xacro",
        "entry": "szlab_poly_powder_container_placeholder_warehouse/models/resource.xacro",
        "macro": "szlab_poly_powder_container_placeholder_warehouse",
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
        "format": "xacro",
        "entry": "szlab_poly_s10_liquid_reagent_placeholder_warehouse/models/resource.xacro",
        "macro": "szlab_poly_s10_liquid_reagent_placeholder_warehouse",
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "szlab_poly_s10_liquid_reagent_placeholder_warehouse/models/shape.yml",
        },
    },
)
def s10_liquid_reagent_placeholder_warehouse(name: str = "试剂瓶堆栈"):
    from szlab_poly_studio.resources.carriers.reagent import SZLab_ReagentBottleStackCarrier

    return SZLab_ReagentBottleStackCarrier(name, fill_placeholders=False)


@resource(
    id="szlab_s04_process_warehouse",
    category=["szlab_poly_studio", "warehouse", "device_mount", "s04_process_warehouse"],
    description="S04 磁搅设备内的 6 个烧杯工位；作为设备子资源承载 Inventory Site。",
)
def s04_process_warehouse(name: str = "S04磁搅工位仓"):
    from szlab_poly_studio.resources.carriers.process_sites import SZLab_S04ProcessCarrier

    return SZLab_S04ProcessCarrier(name)


@resource(
    id="szlab_s05_process_warehouse",
    category=["szlab_poly_studio", "warehouse", "device_mount", "s05_process_warehouse"],
    description="S05 拍照检测设备内的单烧杯工位；作为设备子资源承载 Inventory Site。",
)
def s05_process_warehouse(name: str = "S05拍照工位仓"):
    from szlab_poly_studio.resources.carriers.process_sites import SZLab_S05ProcessCarrier

    return SZLab_S05ProcessCarrier(name)


@resource(
    id="szlab_s06_process_warehouse",
    category=["szlab_poly_studio", "warehouse", "device_mount", "s06_process_warehouse"],
    description="S06 注射泵设备内的单烧杯加液位；作为设备子资源承载 Inventory Site。",
)
def s06_process_warehouse(name: str = "S06加液工位仓"):
    from szlab_poly_studio.resources.carriers.process_sites import SZLab_S06ProcessCarrier

    return SZLab_S06ProcessCarrier(name)


@resource(
    id="szlab_s07_process_warehouse",
    category=["szlab_poly_studio", "warehouse", "device_mount", "s07_process_warehouse"],
    description="S07 固体加料转盘的 10 个粉罐位及 S072 交接位；Pxx 先转到上下料位后由机械臂执行。",
)
def s07_process_warehouse(name: str = "S07固体加料转盘仓"):
    from szlab_poly_studio.resources.carriers.process_sites import SZLab_S07ProcessCarrier

    return SZLab_S07ProcessCarrier(name)
