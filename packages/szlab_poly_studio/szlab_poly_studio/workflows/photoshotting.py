"""S05 拍照与算法结果链路调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_photoshotting = device("szlab_mixer_photoshotting")


@workflow_definition(
    workflow_id="szlab_photoshotting_workflow",
    revision="python-v1",
)
def szlab_photoshotting_workflow(sample_id: str = "debug-sample") -> None:
    szlab_mixer_photoshotting.take_photo(
        sample_id=sample_id,
        photo_path="",
        inspection_result="",
        require_material=False,
    )
