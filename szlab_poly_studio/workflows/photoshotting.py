from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import (
    SzlabMixerPhotoShottingDevice,
)

szlab_mixer_photoshotting: SzlabMixerPhotoShottingDevice = device("szlab_mixer_photoshotting")


@workflow_definition(
    workflow_uuid="ab421e20-1c93-529b-b715-38737edf343b",
    displayname="S05 拍照链路调试",
)
def szlab_photoshotting_workflow(*, sample_id: str = "debug-sample") -> None:
    # unilab:node_uuid=692b3746-83cc-53e2-836c-e8b201b95184
    photo = szlab_mixer_photoshotting.take_photo(  # noqa: F841
        sample_id=sample_id,
        photo_path="",
        inspection_result="",
        require_material=False,
    )
