"""C1 / Host authoring target：最小参数的标准物料转运 Workflow。

标准物理与记账顺序固定为：robot.pick -> robot.place ->
host.transfer_resource。当前 pinned OS 的 host_node authoring surface 还只公开
manual_confirm，imported subworkflow 也仍在 C1 acceptance 中，所以本文件不得登记到
package.yaml；它是冻结接口的目标源码，不是可执行脚本。

Workflow 只传物料、源/目标父 Warehouse、两个局部 Site 和一个
transfer_id。target_device 仅为了满足当前 OS 记账 Action 的显式入参，
不传入机械臂 adapter。
"""

from typing import TypedDict

from unilabos.registry.placeholder_type import DeviceSlot, ResourceSlot
from unilabos.workflow.authoring import device, host_node, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice


robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")


class MaterialTransferResult(TypedDict):
    resource: ResourceSlot
    site: str


@workflow_definition(
    workflow_uuid="e7c53119-9fde-5250-9bf5-264f23d157a8",
    displayname="SZLab 标准物料转运",
    description="物理 pick/place 成功后，唯一一次提交 OS 物料归属。",
    composition_allow_transparent=False,
)
def material_transfer(
    *,
    resource: ResourceSlot,
    source_warehouse: ResourceSlot,
    target_device: DeviceSlot,
    target_warehouse: ResourceSlot,
    source_site: str,
    target_site: str,
    transfer_id: str,
) -> MaterialTransferResult:
    # unilab:node_uuid=bdc83251-7aaa-5fd2-903f-fd2446e25c50
    picked = robot.pick(
        resource=resource,
        warehouse=source_warehouse,
        site=source_site,
        transfer_id=transfer_id,
    )
    # unilab:node_uuid=dd355f49-8bbf-5532-a307-b34de1cbdcb5
    placed = robot.place(
        resource=picked.resource,
        warehouse=target_warehouse,
        site=target_site,
        transfer_id=transfer_id,
    )
    # 只有 place 的 Job 以 SUCCEEDED 终止才可调度本节点；UNKNOWN/失败不得记账。
    # unilab:node_uuid=8d8bfc18-03db-5ff3-a681-edf1c15294b7
    committed = host_node.transfer_resource(
        resource=placed.resource,
        target_device=target_device,
        mount_resource=target_warehouse,
        site=target_site,
    )
    return {"resource": committed.resource, "site": committed.site}
