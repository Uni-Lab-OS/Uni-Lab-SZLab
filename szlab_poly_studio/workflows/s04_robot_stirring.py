from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import SzlabMixerMagneticStirrerDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_robot_device: SzlabMixerRobotDevice = device('szlab_mixer_robot')
szlab_mixer_magnetic_stirrer_device: SzlabMixerMagneticStirrerDevice = device('szlab_mixer_stirrer')


@workflow_definition(
    workflow_uuid='1bc5a151-445a-5a53-b24a-7a4b521ac60c',
    displayname='S04 机械臂与磁搅联调',
)
def s04_机械臂与磁搅联调(
    *,
    position: int = 1,
):
    # unilab:node_uuid=a9ae236b-d422-52c5-8805-9cbe48fa56e1
    placed = szlab_mixer_robot_device.submit_place_to_s04(position=position, sample_id='beaker-1')
    # unilab:node_uuid=2acdc328-6d38-52f2-abbb-badc6664370c
    stirring = szlab_mixer_magnetic_stirrer_device.run_stirring(duration=30.0, mode=3, position=position, reset=False, safe_temperature=80.0, speed=300.0, temperature=25.0)
    # unilab:node_uuid=9d98a536-2855-5644-9a6f-26e8b36d9785
    picked = szlab_mixer_robot_device.submit_pick_from_s04(position=position)
    return {}

