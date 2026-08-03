from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import (
    SzlabMixerPhotoShottingDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_poly_plc.device import SZLabPolyPLCDevice

szlab_poly_plc: SZLabPolyPLCDevice = device("szlab_poly_plc")
szlab_mixer_photoshotting: SzlabMixerPhotoShottingDevice = device("szlab_mixer_photoshotting")
szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


@workflow_definition(
    workflow_uuid="335da2e9-024b-562f-8bf8-35dba0b52a90",
    displayname="堆栈、S05 与 S06 联调",
)
def szlab_stack_s05_s06_workflow() -> None:
    # unilab:node_uuid=7cc804f2-86e3-5a87-9db9-06ecacdf711a
    stack = szlab_poly_plc.get_stack_status()  # noqa: F841
    # unilab:node_uuid=6d6d1ca1-c85d-5c3b-9bac-aa6ecc9651c8
    photo = szlab_mixer_photoshotting.take_photo(  # noqa: F841
        sample_id="debug-sample",
        photo_path="",
        inspection_result="",
        require_material=False,
    )
    # unilab:node_uuid=68fb2497-e52e-545c-9cb4-109de4eb8365
    addition = szlab_mixer_pump.run_solvent_addition(  # noqa: F841
        pump=1,
        volume=8.0,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
