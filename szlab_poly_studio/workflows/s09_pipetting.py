"""S09 移液 local UI preset 的 Python 调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_pipetting_station = device("szlab_mixer_pipetting_station")


@workflow_definition(
    workflow_id="szlab_s09_pipetting_workflow",
    revision="python-v1",
)
def szlab_s09_pipetting_workflow(
    liquid_bottle_index: int = 1,
    volume_ul: float = 100.0,
) -> None:
    szlab_mixer_pipetting_station.prepare_liquid_station()
    szlab_mixer_pipetting_station.bind_sample_to_station(
        sample_id="debug-sample",
    )
    szlab_mixer_pipetting_station.add_liquid(
        liquid_bottle_index=liquid_bottle_index,
        aspirate_volume=volume_ul,
        dispense_volume=volume_ul,
        tip_box_index=1,
        tip_index=1,
        station=1,
        volume_unit="ul",
        skip_level_check=False,
    )
    szlab_mixer_pipetting_station.release_station()
