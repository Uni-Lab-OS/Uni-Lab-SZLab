from unilabos.workflow.authoring import device, workflow_definition, workflow_output

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice

szlab_mixer_robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")
szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


@workflow_definition(
    workflow_uuid="0b4e6fce-14bc-5866-a373-16ad25c7f8cf",
    displayname="S06 机械臂与加液联调",
)
def s06_robot_workflow(*, pump: int = 1, volume: int = 8):
    # unilab:node_uuid=d22f090e-63c7-513e-89eb-6a634dbec638
    placed = szlab_mixer_robot.submit_place_to_s06()  # noqa: F841
    # unilab:node_uuid=a31553c3-8a3d-5c1c-aa16-b759faf6894e
    addition = szlab_mixer_pump.run_solvent_addition(  # noqa: F841
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
    # unilab:node_uuid=2be817c5-3147-5199-b93d-be6e2ce045f8
    picked = szlab_mixer_robot.submit_pick_from_s06()  # noqa: F841
    return workflow_output()
