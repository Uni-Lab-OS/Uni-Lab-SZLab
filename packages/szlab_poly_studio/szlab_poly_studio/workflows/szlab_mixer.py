"""legacy szlab_mixer_workflow.json 的等价 Python 表达。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_pump = device("szlab_mixer_pump")


@workflow_definition(
    workflow_id="szlab_mixer_workflow",
    revision="python-v1",
)
def szlab_mixer_workflow(pump: int = 1, volume: float = 8.0) -> None:
    szlab_mixer_pump.run_solvent_addition(
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=False,
        beaker_true_means_present=True,
    )
