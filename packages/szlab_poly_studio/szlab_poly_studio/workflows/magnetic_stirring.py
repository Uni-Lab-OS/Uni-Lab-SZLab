"""S04 磁搅单工位调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_stirrer = device("szlab_mixer_stirrer")


@workflow_definition(
    workflow_id="szlab_magnetic_stirring_workflow",
    revision="python-v1",
)
def szlab_magnetic_stirring_workflow(
    position: int = 1,
    speed: float = 300.0,
    temperature: float = 25.0,
    duration: float = 30.0,
) -> None:
    szlab_mixer_stirrer.run_stirring(
        position=position,
        mode=3,
        speed=speed,
        temperature=temperature,
        duration=duration,
        safe_temperature=80.0,
        reset=False,
    )
