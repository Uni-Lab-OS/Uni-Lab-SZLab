"""38 动作单样品 JSON 的物料感知 Python 目标表达。

本文件保留为带解释的目标合同，不登记 ``package.yaml``。已规范化并登记生产目录的版本是
``szlab_poly_studio/workflows/single_sample_atomic_material.py``；标准转运使用本轮
``robot.pick -> robot.place -> host.transfer_resource`` 复合 Workflow。下列 typed Action 已在
当前设备包发布：

* ``cap_station.process_cap_with_material``
* ``solid_addition.dose_powder_with_two_materials``
* ``pump.add_solvent_with_materials``
* ``pipetting.add_liquid_with_materials``
* ``stirrer.stir_beaker``
* ``photoshotting.inspect_beaker``
* ``robot.pour_beaker_into_vial``

S08/S09 Site owner、250 mL 样品瓶负载和 S09 试剂瓶在位见证仍是现场生产部署门禁。
不得为了让本目标“可运行”而回退到 ``submit_*``、伪造见证或跳过 Host 记账。
启动图已唯一确定的 Warehouse 直接使用 ``resource_ref("启动资源 ID")``；Site 全部保留为
各 Action/复合 Workflow 调用点的内部 literal。当前仅 S08/S09 尚无启动图 Warehouse 实例，
因此暂时保留这两个 ``ResourceSlot`` 输入。
"""

from typing import Annotated, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.ros.nodes.presets.host_node import HostNode
from unilabos.workflow.authoring import (
    MaterialFlowRole,
    device,
    group,
    material_source,
    parallel,
    resource_ref,
    workflow_definition,
)

from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import (
    SzlabMixerPhotoShottingDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
    SzlabMixerPipettingStationDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)
from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
    SZLabS08CapStationDevice,
)
from szlab_poly_studio.resources.materials import (
    beaker_500ml,
    liquid_reagent_bottle_100ml,
    pipette_tip,
    powder_container,
    sample_vial_250ml,
)

from .material_transfer_target import material_transfer

robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")
cap_station: SZLabS08CapStationDevice = device("szlab_s08_cap_station")
solid_addition: SZLabS07SolidAdditionDevice = device("szlab_s07_solid_addition")
pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")
pipetting: SzlabMixerPipettingStationDevice = device("szlab_mixer_pipetting_station")
stirrer: SzlabMixerMagneticStirrerDevice = device("szlab_mixer_stirrer")
photoshotting: SzlabMixerPhotoShottingDevice = device("szlab_mixer_photoshotting")
host_node: HostNode = device("host_node")


class SingleSampleMaterialResult(TypedDict):
    product_vial: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(sample_vial_250ml),
    ]
    used_beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
    ]
    reagent_bottle: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(liquid_reagent_bottle_100ml),
    ]
    coarse_powder_cartridge: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(powder_container),
    ]
    fine_powder_cartridge: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(powder_container),
    ]
    tip: Annotated[ResourceSlot, AllowedResourceTemplates(pipette_tip)]
    photo_path: str
    inspection_result: str
    commanded_powder_mass_g: float
    message: str


@workflow_definition(
    workflow_uuid="6d9fb3e2-4dcb-5f23-93b4-74d1b6083393",
    displayname="SZLab 单样品全流程（物料感知目标）",
    description=(
        "把旧 38 动作原子 JSON 改写为 MaterialSource、ResourceSlot、标准机械臂复合转运、"
        "多物料加工与命名 Workflow output。"
    ),
)
def single_sample_atomic_material_workflow(
    *,
    reagent_bottle: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(liquid_reagent_bottle_100ml),
    ],
    tip: Annotated[ResourceSlot, AllowedResourceTemplates(pipette_tip)],
    solvent_pump_1: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(liquid_reagent_bottle_100ml),
    ],
    solvent_pump_2: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(liquid_reagent_bottle_100ml),
    ],
    s08_warehouse: ResourceSlot,
    s09_warehouse: ResourceSlot,
    sample_id: str = "sample-001",
    target_powder_mass_g: Annotated[float, Field(ge=0.001, le=100)] = 1.0,
    volume_pump_1: Annotated[int, Field(ge=0)] = 10,
    volume_pump_2: Annotated[int, Field(ge=0)] = 10,
    pipette_volume_raw: Annotated[int, Field(ge=1)] = 5000,
) -> SingleSampleMaterialResult:
    # 原 JSON 没有物料节点。以下四个节点在 Task admission 时解析具体物料并预留。
    # unilab:node_uuid=c6551edc-856a-55f8-91a3-d9c7243fb636
    source_beaker = material_source(
        resource_template=beaker_500ml,
        mode="existing",
        mount=resource_ref("s3_unused_beaker"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.PRIMARY_SAMPLE,
    )
    # unilab:node_uuid=71e3add0-cc3b-5657-8763-2ce15d823077
    source_sample_vial = material_source(
        resource_template=sample_vial_250ml,
        mode="existing",
        mount=resource_ref("s3_unused_beaker"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.CONSUMABLE,
    )
    # unilab:node_uuid=0164a018-80c0-52ac-9350-47e8b5cdec01
    source_coarse_powder = material_source(
        resource_template=powder_container,
        mode="existing",
        mount=resource_ref("powder_container_warehouse"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.REAGENT,
    )
    # unilab:node_uuid=5f3ee9e8-6790-527b-80a8-40f4c5f51cbf
    source_fine_powder = material_source(
        resource_template=powder_container,
        mode="existing",
        mount=resource_ref("powder_container_warehouse"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.REAGENT,
    )

    # [old 6] 扫码只更新/核验 S07 事实，不再用注释伪造条件边。
    # unilab:node_uuid=b46df2d0-42b8-5460-b192-aaf53537579e
    solid_addition.scan_powder_cartridges(timeout=300.0)

    # 五条准备链是无条件并行拓扑。所有 material_transfer 内部都选择同一个 robot，
    # 因而机械臂动作仍由设备 Claim 互斥，其他工站动作可以重叠。
    with parallel():
        with group(name="液体试剂瓶开盖并搬到 S09"):
            # [old 1-2]
            # unilab:node_uuid=e01e23ce-72d2-5136-b849-60fa3fe2525f
            reagent_at_s08 = material_transfer(
                resource=reagent_bottle,
                source_warehouse=resource_ref("s10_liquid_reagent"),
                target_device="szlab_s08_cap_station",
                target_warehouse=s08_warehouse,
                source_site="R1C1",
                target_site="S082",
            )
            # [old 3] required target Action: 同名 container ResourceSlot 透传。
            # unilab:node_uuid=38c2603a-0dac-5930-a26e-966138075939
            opened_reagent = cap_station.process_cap_with_material(
                container=reagent_at_s08.resource,
                operation="open",
                vial_type="liquid_100ml",
                sample_id=sample_id,
                timeout=300.0,
            )
            # [old 4-5]
            # unilab:node_uuid=c0a01cc2-507c-5d28-84bd-192079cd7d59
            reagent_at_s09 = material_transfer(
                resource=opened_reagent.container,
                source_warehouse=s08_warehouse,
                target_device="szlab_mixer_pipetting_station",
                target_warehouse=s09_warehouse,
                source_site="S082",
                target_site="REAGENT1",
            )

        with group(name="粗注粉瓶搬到 S07 P01"):
            # [old 9 的 S07 转位部分]
            # unilab:node_uuid=671c77fc-56a4-5512-82f9-de6ce25d4e8a
            prepared_coarse = solid_addition.prepare_powder_cartridge_site(
                powder_cartridge=source_coarse_powder,
                powder_site="P01",
                timeout=300.0,
            )
            # [old 9 的取料部分 + old 10]
            # unilab:node_uuid=3f8eab79-f12d-52df-b66b-8a4efa04529d
            coarse_at_s07 = material_transfer(
                resource=prepared_coarse.powder_cartridge,
                source_warehouse=resource_ref("powder_container_warehouse"),
                target_device="szlab_s07_solid_addition",
                target_warehouse=resource_ref("s07_process_warehouse"),
                source_site="L1C1",
                target_site="P01",
            )

        with group(name="精注粉瓶搬到 S07 P02"):
            # [old 13 的 S07 转位部分]
            # unilab:node_uuid=a522d335-ccc7-5942-a7eb-669cfc6942a9
            prepared_fine = solid_addition.prepare_powder_cartridge_site(
                powder_cartridge=source_fine_powder,
                powder_site="P02",
                timeout=300.0,
            )
            # [old 13 的取料部分 + old 14]
            # unilab:node_uuid=3754171f-01a2-51b7-af0e-64512996226b
            fine_at_s07 = material_transfer(
                resource=prepared_fine.powder_cartridge,
                source_warehouse=resource_ref("powder_container_warehouse"),
                target_device="szlab_s07_solid_addition",
                target_warehouse=resource_ref("s07_process_warehouse"),
                source_site="L1C2",
                target_site="P02",
            )

        with group(name="烧杯搬到 S07 交接位"):
            # [old 15-16]
            # unilab:node_uuid=db81cbea-7f28-5a86-94a0-13864cfb1fa5
            beaker_at_s07 = material_transfer(
                resource=source_beaker,
                source_warehouse=resource_ref("s3_unused_beaker"),
                target_device="szlab_s07_solid_addition",
                target_warehouse=resource_ref("s07_process_warehouse"),
                source_site="L1B1",
                target_site="S0721",
            )

        with group(name="样品瓶搬到 S08 并开盖"):
            # [old 27-28] 从旧串行位置前移；与其他准备链没有材料依赖。
            # unilab:node_uuid=8eb012b4-f12a-5d61-a675-3bd68147ca85
            sample_vial_at_s08 = material_transfer(
                resource=source_sample_vial,
                source_warehouse=resource_ref("s3_unused_beaker"),
                target_device="szlab_s08_cap_station",
                target_warehouse=s08_warehouse,
                source_site="L1A1",
                target_site="S081",
            )
            # [old 29]
            # unilab:node_uuid=05fcfaa8-f511-519e-b29b-b6035086fd93
            opened_sample_vial = cap_station.process_cap_with_material(
                container=sample_vial_at_s08.resource,
                operation="open",
                vial_type="sample_250ml",
                sample_id=sample_id,
                timeout=300.0,
            )

    # [old 17] 三条 required material input 直接形成 AND 汇合，无 synthetic Join。
    # unilab:node_uuid=64cae18e-a070-5ceb-bc09-997c53e35e1f
    dosed = solid_addition.dose_powder_with_two_materials(
        coarse_powder_cartridge=coarse_at_s07.resource,
        fine_powder_cartridge=fine_at_s07.resource,
        beaker=beaker_at_s07.resource,
        coarse_powder_site="P01",
        fine_powder_site="P02",
        target_mass_g=target_powder_mass_g,
        recipe_name="default",
        params_json=None,
        timeout=300.0,
    )

    # [old 18-19]
    # unilab:node_uuid=618aaeda-ffba-5d74-b9f8-93366cd11e4b
    beaker_at_s06 = material_transfer(
        resource=dosed.beaker,
        source_warehouse=resource_ref("s07_process_warehouse"),
        target_device="szlab_mixer_pump",
        target_warehouse=resource_ref("s06_process_warehouse"),
        source_site="S0721",
        target_site="S061",
    )
    # [old 20] 新合同补出旧 JSON 缺失的两路溶剂 ResourceSlot。
    # unilab:node_uuid=00e72600-5c9c-5afd-9c70-338d6eddc102
    added_solvents = pump.add_solvent_with_materials(
        beaker=beaker_at_s06.resource,
        solvent_pump_1=solvent_pump_1,
        solvent_pump_2=solvent_pump_2,
        volume_pump_1=volume_pump_1,
        volume_pump_2=volume_pump_2,
        skip_level_check=False,
        beaker_true_means_present=True,
    )

    # [old 21-22]
    # unilab:node_uuid=96db2ac9-4cb9-5242-b1b7-63e81c416aa4
    beaker_at_s09 = material_transfer(
        resource=added_solvents.beaker,
        source_warehouse=resource_ref("s06_process_warehouse"),
        target_device="szlab_mixer_pipetting_station",
        target_warehouse=s09_warehouse,
        source_site="S061",
        target_site="BEAKER1",
    )
    # [old 23] 烧杯、试剂瓶和 TIP 是三个独立 material input。
    # unilab:node_uuid=c535cf80-22f3-5f92-9222-020d66f8b3ea
    pipetted = pipetting.add_liquid_with_materials(
        beaker=beaker_at_s09.resource,
        reagent_bottle=reagent_at_s09.resource,
        tip=tip,
        liquid_bottle_index=1,
        station=1,
        aspirate_volume=pipette_volume_raw,
        dispense_volume=pipette_volume_raw,
        volume_unit="raw",
        skip_level_check=False,
    )

    # [old 24-25]
    # unilab:node_uuid=6ade06a7-f2e8-57f5-8d29-8124d303e43e
    beaker_at_s04 = material_transfer(
        resource=pipetted.beaker,
        source_warehouse=s09_warehouse,
        target_device="szlab_mixer_stirrer",
        target_warehouse=resource_ref("s04_process_warehouse"),
        source_site="BEAKER1",
        target_site="S041",
    )
    # [old 26]
    # unilab:node_uuid=ffa0066c-b9c2-5d37-aff3-bfac6481b01c
    stirred = stirrer.stir_beaker(
        beaker=beaker_at_s04.resource,
        position=1,
        mode=3,
        speed=300,
        temperature=25,
        duration=30.0,
        safe_temperature=80,
        reset=False,
    )

    # [old 30-31]
    # unilab:node_uuid=5aff8d44-869d-503b-85e1-abca3da3980b
    beaker_at_s05 = material_transfer(
        resource=stirred.beaker,
        source_warehouse=resource_ref("s04_process_warehouse"),
        target_device="szlab_mixer_photoshotting",
        target_warehouse=resource_ref("s05_process_warehouse"),
        source_site="S041",
        target_site="S051",
    )
    # [old 32]
    # unilab:node_uuid=ea651e5f-bbdd-580c-a3ce-75ff7f30da7c
    inspected = photoshotting.inspect_beaker(
        beaker=beaker_at_s05.resource,
        sample_id=sample_id,
        photo_path="",
        inspection_result="",
    )

    # [old 33-35] 倒料是“持杯加工”而非普通点到点搬运，不能伪装成 transfer。
    # OS 在最终 place 成功前仍保留 S05 归属，并由同一 Execution Claim 冻结烧杯、样品瓶和 Site。
    # unilab:node_uuid=c3305a3e-c047-5c64-be13-18fd07c85436
    picked_for_pour = robot.pick(
        resource=inspected.beaker,
        warehouse=resource_ref("s05_process_warehouse"),
        site="S051",
    )
    # unilab:node_uuid=c50f7c2c-b4b6-5c3b-be91-25675bb0d842
    poured = robot.pour_beaker_into_vial(
        beaker=picked_for_pour.resource,
        sample_vial=opened_sample_vial.container,
        sample_vial_site="S081",
    )

    # 倒料完成后，回收烧杯与关盖没有数据依赖，可并行；S08/机械臂各自有设备 Claim。
    with parallel():
        with group(name="使用后烧杯回 S11"):
            # unilab:node_uuid=3f4d4079-8964-5414-803a-8dc4873498b5
            placed_used_beaker = robot.place(
                resource=poured.beaker,
                warehouse=resource_ref("s11_used_beaker"),
                site="L1B1",
            )
            # unilab:node_uuid=99d2a553-bcaa-5a69-a302-953f28790fcd
            committed_used_beaker = host_node.transfer_resource(
                resource=placed_used_beaker.resource,
                target_device="host_node",
                mount_resource=resource_ref("s11_used_beaker"),
                site="L1B1",
            )

        with group(name="S08 关闭成品样品瓶"):
            # [old 36]
            # unilab:node_uuid=f7a8bda7-0ebf-5752-9598-1ef2c7f90fe3
            closed_sample_vial = cap_station.process_cap_with_material(
                container=poured.sample_vial,
                operation="close",
                vial_type="sample_250ml",
                sample_id=sample_id,
                timeout=300.0,
            )

    # [old 37-38]
    # unilab:node_uuid=8436dc02-a9f3-5286-9822-6e5d22ae4205
    product_vial_at_s11 = material_transfer(
        resource=closed_sample_vial.container,
        source_warehouse=s08_warehouse,
        target_device="host_node",
        target_warehouse=resource_ref("s11_used_beaker"),
        source_site="S081",
        target_site="L1A1",
    )

    return {
        "product_vial": product_vial_at_s11.resource,
        "used_beaker": committed_used_beaker.resource,
        "reagent_bottle": pipetted.reagent_bottle,
        "coarse_powder_cartridge": dosed.coarse_powder_cartridge,
        "fine_powder_cartridge": dosed.fine_powder_cartridge,
        "tip": pipetted.tip,
        "photo_path": inspected.photo_path,
        "inspection_result": inspected.inspection_result,
        "commanded_powder_mass_g": dosed.commanded_mass_g,
        "message": "single sample material workflow completed",
    }
