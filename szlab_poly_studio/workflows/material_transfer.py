from typing import TypedDict

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from unilabos.ros.nodes.presets.host_node import HostNode
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import device, workflow_definition


class SZLab标准物料转运Result(TypedDict):
    site: str


szlabmixerrobotdevice: SzlabMixerRobotDevice = device('szlab_mixer_robot')
hostnode: HostNode = device('host_node')


@workflow_definition(
    workflow_uuid="e7c53119-9fde-5250-9bf5-264f23d157a8",
    displayname='SZLab 标准物料转运',
    description='对任意 ResourceSlot 执行统一 pick/place，并在成功后唯一一次提交 OS 物料归属；材料类型由同名隐式输出保持。',
)
def s_z_lab_标准物料转运(
    *,
    resource: ResourceSlot,
    source_warehouse: ResourceSlot,
    target_device: str,
    target_warehouse: ResourceSlot,
    source_site: str,
    target_site: str,
) -> SZLab标准物料转运Result:
    # unilab:node_uuid=bdc83251-7aaa-5fd2-903f-fd2446e25c50
    picked = szlabmixerrobotdevice.pick(resource=resource, site=source_site, warehouse=source_warehouse)
    # unilab:node_uuid=dd355f49-8bbf-5532-a307-b34de1cbdcb5
    placed = szlabmixerrobotdevice.place(resource=picked.resource, site=target_site, warehouse=target_warehouse)
    # unilab:node_uuid=8d8bfc18-03db-5ff3-a681-edf1c15294b7
    committed = hostnode.transfer_resource(mount_resource=target_warehouse, resource=placed.resource, site=target_site, target_device=target_device)
    return {'site': committed.site}
