from typing import Annotated, TypedDict
from pydantic import Field
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import SZLabS07SolidAdditionDevice
from unilabos.ros.nodes.presets.host_node import HostNode
from szlab_poly_studio.resources.materials import beaker_500ml
from szlab_poly_studio.resources.materials import powder_container
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import MaterialFlowRole, device, group, material_source, parallel, resource_ref, workflow_definition


class S07粉桶与烧杯搬运后固体称量Result(TypedDict):
    beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]
    powder_cartridge: Annotated[ResourceSlot, AllowedResourceTemplates(powder_container)]
    commanded_mass_g: float
    message: str


szlab_mixer_robot_device: SzlabMixerRobotDevice = device('szlab_mixer_robot')
s_z_lab_s07_solid_addition_device: SZLabS07SolidAdditionDevice = device('szlab_s07_solid_addition')
host_node: HostNode = device('host_node')


@workflow_definition(
    workflow_uuid='5e7ce142-bf5a-5d30-8666-fdf5374941f1',
    displayname='S07 粉桶与烧杯搬运后固体称量',
    description='粉桶从固体粉桶堆栈搬入 S07 指定 Pxx，烧杯从 S03 搬入 S072；物理动作确认后由 Host 记账，再执行物料感知投粉。',
)
def s07_粉桶与烧杯搬运后固体称量(
    *,
    solid_addition_device_id: str = 'szlab_s07_solid_addition',
    target_mass_g: Annotated[float, Field(ge=0.001, le=100)] = 1.0,
    recipe_name: str = 'default',
) -> S07粉桶与烧杯搬运后固体称量Result:
    # unilab:node_uuid=af599d17-1d6c-5f34-a2f1-dc5239d1275d
    source_beaker = material_source(resource_template=beaker_500ml, mode='existing', mount=resource_ref('s3_unused_beaker'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.PRIMARY_SAMPLE)
    # unilab:node_uuid=f7969031-098d-52eb-9193-92e41de3f3da
    source_powder = material_source(resource_template=powder_container, mode='existing', mount=resource_ref('powder_container_warehouse'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.REAGENT)
    with parallel():
        # unilab:node_uuid=115b2549-9202-518c-9aac-0a71de8ba72f
        with group(name='烧杯搬运'):
            # unilab:node_uuid=4058067c-18e2-5b35-90eb-ddf04694c040
            picked_beaker = szlab_mixer_robot_device.pick(resource=source_beaker, site='L1B1', warehouse=resource_ref('s3_unused_beaker'))
            # unilab:node_uuid=6c673893-36e1-5674-aeeb-8bac8c9197c4
            placed_beaker = szlab_mixer_robot_device.place(resource=picked_beaker.resource, site='S0722', warehouse=resource_ref('s07_process_warehouse'))
            # unilab:node_uuid=65fbc7bf-5e17-5a3e-9b15-eab6ebebbf82
            committed_beaker = host_node.transfer_resource(mount_resource=resource_ref('s07_process_warehouse'), resource=placed_beaker.resource, site='S0722', target_device=solid_addition_device_id)
        # unilab:node_uuid=b6337f56-31f2-55c1-ab9d-f44e1b956e50
        with group(name='粉桶搬运'):
            # unilab:node_uuid=9f67e05d-020a-5e8d-bf86-ae812aac7c01
            picked_powder = szlab_mixer_robot_device.pick(resource=source_powder, site='L1C1', warehouse=resource_ref('powder_container_warehouse'))
            # unilab:node_uuid=7394a0a0-b08e-541e-9403-0c9898e06936
            prepared_powder = s_z_lab_s07_solid_addition_device.prepare_powder_cartridge_site(powder_cartridge=picked_powder.resource, powder_site='P01', timeout=300.0)
            # unilab:node_uuid=45ffc4a3-ab9e-5805-a2f6-673c35989d2f
            placed_powder = szlab_mixer_robot_device.place(resource=prepared_powder.powder_cartridge, site='P01', warehouse=resource_ref('s07_process_warehouse'))
            # unilab:node_uuid=c776a7e8-01b4-4a15-b0eb-a201e865cb2a
            committed_powder = host_node.transfer_resource(mount_resource=resource_ref('s07_process_warehouse'), resource=placed_powder.resource, site='P01', target_device=solid_addition_device_id)
    # unilab:node_uuid=58198f7a-eec4-5276-9bc5-5dd5b54c4b06
    dosed = s_z_lab_s07_solid_addition_device.dose_powder_with_materials(beaker=committed_beaker.resource, params_json=None, powder_cartridge=committed_powder.resource, powder_site='P01', recipe_name=recipe_name, target_mass_g=target_mass_g, timeout=300.0)
    return {'beaker': dosed.beaker, 'powder_cartridge': dosed.powder_cartridge, 'commanded_mass_g': dosed.commanded_mass_g, 'message': dosed.message}
