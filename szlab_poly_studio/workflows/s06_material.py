from typing import TypedDict

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.resources.materials import beaker_500ml
from unilabos.ros.nodes.presets.host_node import HostNode
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import device, workflow, MaterialFlowRole, material_source, resource_ref


class S06搬运加液Result(TypedDict):
    beaker: ResourceSlot
    message: str


szlabmixerpumpdevice: SzlabMixerPumpDevice = device('szlab_mixer_pump')
szlabmixerrobotdevice: SzlabMixerRobotDevice = device('szlab_mixer_robot')
hostnode: HostNode = device('host_node')


@workflow(
    workflow_uuid="f372fd2d-447e-5f97-85e4-f90628e9f472",
    displayname='S06 搬运加液',
    description='从 S03 获取现有 500 mL 烧杯，按标准物料转运合同搬入 S06；物理动作成功后由 Host 提交物料归属，再执行物料感知加液。',
)
def szlab_material_s06_workflow(
    *,
    pump: int = 1,
    volume: int = 8,
) -> S06搬运加液Result:
    # unilab:node_uuid=27001d16-d1e8-541a-832b-6e23660bcb12
    source_beaker = material_source(resource_template=beaker_500ml, mode='existing', mount=resource_ref("s3_unused_beaker"), material_uuid='fd9ab57f-dcc8-5636-a65f-d304a5fa87ae', site=None, slot_range=None, flow_role=MaterialFlowRole.PRIMARY_SAMPLE)
    # unilab:node_uuid=9c35ad8e-dbb9-5824-af71-34a81a6bb1d0
    picked = szlabmixerrobotdevice.pick(resource=source_beaker, site='L1B1', warehouse=resource_ref("s3_unused_beaker"))
    # unilab:node_uuid=e357c916-fb2d-5e5c-bea5-7eb5e69def5c
    placed = szlabmixerrobotdevice.place(resource=picked.resource, site='S061', warehouse=resource_ref("s06_process_warehouse"))
    # unilab:node_uuid=00f1887d-e991-584d-a7eb-45b3794a253c
    committed = hostnode.transfer_resource(mount_resource=resource_ref("s06_process_warehouse"), resource=placed.resource, site='S061', target_device='szlab_mixer_pump')
    # unilab:node_uuid=fd5fc6bf-a26b-54af-8bb0-68fd377a7394
    addition = szlabmixerpumpdevice.add_solvent_to_beaker(beaker=committed.resource, beaker_true_means_present=True, pump=pump, skip_level_check=False, volume=volume)
    return {'beaker': addition.beaker, 'message': addition.message}
