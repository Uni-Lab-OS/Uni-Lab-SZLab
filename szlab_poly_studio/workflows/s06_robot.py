"""legacy s06_robot_workflow.json 的等价 Python 表达。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_robot = device("szlab_mixer_robot")
szlab_mixer_pump = device("szlab_mixer_pump")


@workflow_definition(
    workflow_id="s06_robot_workflow",
    revision="python-v1",
)
def s06_robot_workflow(pump: int = 1, volume: float = 8.0) -> None:
    szlab_mixer_robot.submit_place_to_s06()
    szlab_mixer_pump.run_solvent_addition(
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
    szlab_mixer_robot.submit_pick_from_s06()
