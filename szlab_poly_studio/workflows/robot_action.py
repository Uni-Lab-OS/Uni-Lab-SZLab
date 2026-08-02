from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice

szlab_mixer_robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")


@workflow_definition(
    workflow_uuid="25166c6a-2e85-5008-ba3c-03d742ef9b1a",
    displayname="机械臂单工位取放调试",
)
def szlab_robot_action_workflow(*, position: int = 1) -> None:
    # unilab:node_uuid=1ab6e8b9-0e11-59d9-aa11-2213fbd43a1b
    placed = szlab_mixer_robot.submit_place_to_s04(  # noqa: F841
        position=position,
        sample_id="debug-beaker",
    )
    # unilab:node_uuid=16d36efa-a735-5a13-bb9d-23658f3f53cd
    picked = szlab_mixer_robot.submit_pick_from_s04(position=position)  # noqa: F841
