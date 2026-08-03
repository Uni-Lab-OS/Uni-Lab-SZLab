"""机器人转运、S06 加液与 S04 搅拌五节点演示。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_robot = device("szlab_mixer_robot")
szlab_mixer_pump = device("szlab_mixer_pump")
szlab_mixer_stirrer = device("szlab_mixer_stirrer")


@workflow_definition(
    workflow_id="szlab_robot_liquid_stirring_demo_workflow",
    revision="python-v1",
)
def szlab_robot_liquid_stirring_demo_workflow(
    pump: int = 1,
    volume: float = 8.0,
    position: int = 1,
    speed: float = 300.0,
    temperature: float = 25.0,
    duration: float = 30.0,
) -> None:
    szlab_mixer_robot.submit_place_to_s06()
    szlab_mixer_pump.run_solvent_addition(
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
    szlab_mixer_robot.submit_pick_from_s06()
    szlab_mixer_robot.submit_place_to_s04(
        position=position,
        sample_id="demo-beaker",
    )
    szlab_mixer_stirrer.run_stirring(
        position=position,
        mode=3,
        speed=speed,
        temperature=temperature,
        duration=duration,
        safe_temperature=80.0,
        reset=False,
    )
