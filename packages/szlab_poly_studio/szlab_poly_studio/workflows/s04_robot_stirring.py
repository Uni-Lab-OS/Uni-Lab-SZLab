"""legacy s04_robot_stirring_workflow.json 的等价 Python 表达。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_robot = device("szlab_mixer_robot")
szlab_mixer_stirrer = device("szlab_mixer_stirrer")


@workflow_definition(
    workflow_id="s04_robot_stirring_workflow",
    revision="python-v1",
)
def s04_robot_stirring_workflow(position: int = 1) -> None:
    szlab_mixer_robot.submit_place_to_s04(
        position=position,
        sample_id="beaker-1",
    )
    szlab_mixer_stirrer.run_stirring(
        position=position,
        mode=3,
        speed=300.0,
        temperature=25.0,
        duration=30.0,
        safe_temperature=80.0,
        reset=False,
    )
    szlab_mixer_robot.submit_pick_from_s04(position=position)
