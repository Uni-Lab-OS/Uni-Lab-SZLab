from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_pump_device: SzlabMixerPumpDevice = device('szlab_mixer_pump')
szlab_mixer_robot_device: SzlabMixerRobotDevice = device('szlab_mixer_robot')


@workflow_definition(
    workflow_uuid='0b4e6fce-14bc-5866-a373-16ad25c7f8cf',
    displayname='S06 机械臂与加液联调',
)
def s06_机械臂与加液联调(
    *,
    pump: int = 1,
    volume: int = 8,
) -> None:
    # unilab:node_uuid=d22f090e-63c7-513e-89eb-6a634dbec638
    placed = szlab_mixer_robot_device.submit_place_to_s06()
    # unilab:node_uuid=a31553c3-8a3d-5c1c-aa16-b759faf6894e
    addition = szlab_mixer_pump_device.run_solvent_addition(beaker_true_means_present=True, process=1, pump=pump, skip_level_check=False, skip_robot=True, volume=volume, volume_pump_1=1, volume_pump_2=1)
    # unilab:node_uuid=2be817c5-3147-5199-b93d-be6e2ce045f8
    picked = szlab_mixer_robot_device.submit_pick_from_s06()
