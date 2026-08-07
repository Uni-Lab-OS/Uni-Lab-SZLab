from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_robot_device: SzlabMixerRobotDevice = device('szlab_mixer_robot')


@workflow_definition(
    workflow_uuid='4f6ec98a-d3e1-580b-a72e-8ce4fe9d5def',
    displayname='S07 机械臂联调',
)
def s07_机械臂联调():
    # unilab:node_uuid=204657ba-491b-5e6a-bbf2-f6ddd1d720ec
    placed_s071 = szlab_mixer_robot_device.submit_place_to_s071(position='1-1')
    # unilab:node_uuid=9c5505ab-bd02-5c84-ae7e-744aaea8cd5e
    placed_s072 = szlab_mixer_robot_device.submit_place_to_s072(position=1, product_type=1)
    # unilab:node_uuid=f71f4aca-fa51-54c0-a385-1d77a83f6f27
    picked_s072 = szlab_mixer_robot_device.submit_pick_from_s072(position=1, product_type=1)
    return {}

