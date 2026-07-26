"""堆栈状态、S05 拍照和 S06 加液的联合调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_poly_plc = device("szlab_poly_plc")
szlab_mixer_photoshotting = device("szlab_mixer_photoshotting")
szlab_mixer_pump = device("szlab_mixer_pump")


@workflow_definition(
    workflow_id="szlab_stack_s05_s06_workflow",
    revision="python-v1",
)
def szlab_stack_s05_s06_workflow() -> None:
    szlab_poly_plc.get_stack_status()
    szlab_mixer_photoshotting.take_photo(
        sample_id="debug-sample",
        photo_path="",
        inspection_result="",
        require_material=False,
    )
    szlab_mixer_pump.run_solvent_addition(
        pump=1,
        volume=8.0,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
