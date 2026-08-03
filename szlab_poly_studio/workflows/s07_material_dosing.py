# Wayfinder 目标：粉桶、烧杯搬运与 S07 物料感知固体称量流程。
# host_node.transfer_resource 进入 typed Action Catalog 后再登记 package.yaml。

from typing import Annotated, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.ros.nodes.presets.host_node import HostNode
from unilabos.workflow.authoring import (
    MaterialFlowRole,
    device,
    material_source,
    resource_ref,
    workflow_definition,
)

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)
from szlab_poly_studio.resources.materials import beaker_500ml, powder_container

robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")
solid_addition: SZLabS07SolidAdditionDevice = device("szlab_s07_solid_addition")
host_node: HostNode = device("host_node")


class S07MaterialDosingResult(TypedDict):
    beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]
    powder_cartridge: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(powder_container),
    ]
    commanded_mass_g: float
    message: str


@workflow_definition(
    workflow_uuid="5e7ce142-bf5a-5d30-8666-fdf5374941f1",
    displayname="S07 粉桶与烧杯搬运后固体称量",
    description=(
        "粉桶从固体粉桶堆栈搬入 S07 指定 Pxx，烧杯从 S03 搬入 S072；"
        "物理动作确认后由 Host 记账，再执行物料感知投粉。"
    ),
)
def s07_material_dosing(
    *,
    powder_source_warehouse: ResourceSlot,
    beaker_source_warehouse: ResourceSlot,
    solid_addition_warehouse: ResourceSlot,
    powder_source_site: str,
    powder_target_site: str,
    beaker_source_site: str,
    beaker_target_site: str,
    powder_transfer_id: str,
    beaker_transfer_id: str,
    target_mass_g: Annotated[float, Field(ge=0.001, le=100)] = 1.0,
    recipe_name: str = "default",
) -> S07MaterialDosingResult:
    # unilab:node_uuid=f7969031-098d-52eb-9193-92e41de3f3da
    source_powder = material_source(
        resource_template=powder_container,
        mode="existing",
        mount=resource_ref("fa7b0692-2e78-5d5e-b789-9b0dfffb5dc7"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.REAGENT,
    )
    # unilab:node_uuid=af599d17-1d6c-5f34-a2f1-dc5239d1275d
    source_beaker = material_source(
        resource_template=beaker_500ml,
        mode="existing",
        mount=resource_ref("29f43434-ff8b-5246-b924-a20cddd452fc"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.PRIMARY_SAMPLE,
    )

    # 粉桶先从独立堆栈取出；Pxx 在放入前由 S07 呈现到已验证上下料位。
    # unilab:node_uuid=9f67e05d-020a-5e8d-bf86-ae812aac7c01
    picked_powder = robot.pick(
        resource=source_powder,
        warehouse=powder_source_warehouse,
        site=powder_source_site,
        transfer_id=powder_transfer_id,
    )
    # unilab:node_uuid=7394a0a0-b08e-541e-9403-0c9898e06936
    prepared_powder = solid_addition.prepare_powder_cartridge_site(
        powder_cartridge=picked_powder.resource,
        powder_site=powder_target_site,
        timeout=300.0,
    )
    # unilab:node_uuid=45ffc4a3-ab9e-5805-a2f6-673c35989d2f
    placed_powder = robot.place(
        resource=prepared_powder.powder_cartridge,
        warehouse=solid_addition_warehouse,
        site=powder_target_site,
        transfer_id=powder_transfer_id,
    )
    # unilab:node_uuid=8d8bfc18-03db-5ff3-a681-edf1c15294b7
    committed_powder = host_node.transfer_resource(
        resource=placed_powder.resource,
        target_device=solid_addition,
        mount_resource=solid_addition_warehouse,
        site=powder_target_site,
    )

    # 粉桶进入转盘后再占用同一机器人/S072 区域搬运烧杯。
    # unilab:node_uuid=4058067c-18e2-5b35-90eb-ddf04694c040
    picked_beaker = robot.pick(
        resource=source_beaker,
        warehouse=beaker_source_warehouse,
        site=beaker_source_site,
        transfer_id=beaker_transfer_id,
    )
    # unilab:node_uuid=6c673893-36e1-5674-aeeb-8bac8c9197c4
    placed_beaker = robot.place(
        resource=picked_beaker.resource,
        warehouse=solid_addition_warehouse,
        site=beaker_target_site,
        transfer_id=beaker_transfer_id,
    )
    # unilab:node_uuid=65fbc7bf-5e17-5a3e-9b15-eab6ebebbf82
    committed_beaker = host_node.transfer_resource(
        resource=placed_beaker.resource,
        target_device=solid_addition,
        mount_resource=solid_addition_warehouse,
        site=beaker_target_site,
    )

    # unilab:node_uuid=58198f7a-eec4-5276-9bc5-5dd5b54c4b06
    dosed = solid_addition.dose_powder_with_materials(
        powder_cartridge=committed_powder.resource,
        beaker=committed_beaker.resource,
        powder_site=powder_target_site,
        target_mass_g=target_mass_g,
        recipe_name=recipe_name,
        params_json=None,
        timeout=300.0,
    )
    return {
        "beaker": dosed.beaker,
        "powder_cartridge": dosed.powder_cartridge,
        "commanded_mass_g": dosed.commanded_mass_g,
        "message": dosed.message,
    }
