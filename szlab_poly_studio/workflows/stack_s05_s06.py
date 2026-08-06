from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import SzlabMixerPhotoShottingDevice
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_poly_plc.device import SZLabPolyPLCDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_photo_shotting_device: SzlabMixerPhotoShottingDevice = device('szlab_mixer_photoshotting')
szlab_mixer_pump_device: SzlabMixerPumpDevice = device('szlab_mixer_pump')
s_z_lab_poly_p_l_c_device: SZLabPolyPLCDevice = device('szlab_poly_plc')


@workflow_definition(
    workflow_uuid='335da2e9-024b-562f-8bf8-35dba0b52a90',
    displayname='堆栈、S05 与 S06 联调',
)
def 堆栈__s05_与__s06_联调() -> None:
    # unilab:node_uuid=7cc804f2-86e3-5a87-9db9-06ecacdf711a
    stack = s_z_lab_poly_p_l_c_device.get_stack_status(group_names=None)
    # unilab:node_uuid=6d6d1ca1-c85d-5c3b-9bac-aa6ecc9651c8
    photo = szlab_mixer_photo_shotting_device.take_photo(inspection_result='', photo_path='', require_material=False, sample_id='debug-sample')
    # unilab:node_uuid=68fb2497-e52e-545c-9cb4-109de4eb8365
    addition = szlab_mixer_pump_device.run_solvent_addition(beaker_true_means_present=True, process=1, pump=1, skip_level_check=False, skip_robot=True, volume=8.0, volume_pump_1=1, volume_pump_2=1)
