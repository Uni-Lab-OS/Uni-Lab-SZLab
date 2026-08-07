from typing import TypedDict

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import SzlabMixerMagneticStirrerDevice
from szlab_poly_studio.resources.materials import beaker_500ml
from unilabos.ros.nodes.presets.host_node import HostNode
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import device, workflow, MaterialFlowRole, material_source, resource_ref


class S04搬运搅拌Result(TypedDict):
    beaker: ResourceSlot
    message: str


szlabmixerrobotdevice: SzlabMixerRobotDevice = device('szlab_mixer_robot')
szlabmixermagneticstirrerdevice: SzlabMixerMagneticStirrerDevice = device('szlab_mixer_stirrer')
hostnode: HostNode = device('host_node')


@workflow(
    workflow_uuid="1bc5a151-445a-5a53-b24a-7a4b521ac60c",
    displayname='S04 搬运搅拌',
    description='从 S03 获取现有 500 mL 烧杯，按标准物料转运合同搬入 S041；物理动作成功后由 Host 提交物料归属，再执行物料感知磁搅。',
)
def s04_robot_stirring_workflow(
    *,
    mode: int = 3,
    speed: int = 300,
    temperature: int = 25,
    duration: float = 30.0,
    safe_temperature: int = 80,
) -> S04搬运搅拌Result:
    # unilab:node_uuid=789a288f-28ad-55d9-a8a8-d018d24dfb78
    source_beaker = material_source(resource_template=beaker_500ml, mode='existing', mount=resource_ref("s3_unused_beaker"), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.PRIMARY_SAMPLE)
    # unilab:node_uuid=7c686f7b-60de-521d-9fe2-b6daf7533616
    picked = szlabmixerrobotdevice.pick(resource=source_beaker, site='L1B1', warehouse=resource_ref("s3_unused_beaker"))
    # unilab:node_uuid=a9ae236b-d422-52c5-8805-9cbe48fa56e1
    placed = szlabmixerrobotdevice.place(resource=picked.resource, site='S041', warehouse=resource_ref("s04_process_warehouse"))
    # unilab:node_uuid=d771321b-af35-5f80-80cb-195df67f9a0c
    committed = hostnode.transfer_resource(mount_resource=resource_ref("s04_process_warehouse"), resource=placed.resource, site='S041', target_device='szlab_mixer_stirrer')
    # unilab:node_uuid=2acdc328-6d38-52f2-abbb-badc6664370c
    stirred = szlabmixermagneticstirrerdevice.stir_beaker(beaker=committed.resource, duration=duration, mode=mode, position=1, reset=False, safe_temperature=safe_temperature, speed=speed, temperature=temperature)
    return {'beaker': stirred.beaker, 'message': stirred.message}
