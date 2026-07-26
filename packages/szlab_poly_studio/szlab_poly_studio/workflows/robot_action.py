"""机械臂单工位取放调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_robot = device("szlab_mixer_robot")


@workflow_definition(
    workflow_id="szlab_robot_action_workflow",
    revision="python-v1",
)
def szlab_robot_action_workflow(position: int = 1) -> None:
    szlab_mixer_robot.submit_place_to_s04(
        position=position,
        sample_id="debug-beaker",
    )
    szlab_mixer_robot.submit_pick_from_s04(position=position)
