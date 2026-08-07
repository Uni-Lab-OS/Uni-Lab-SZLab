from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_pump_device: SzlabMixerPumpDevice = device('szlab_mixer_pump')


@workflow_definition(
    workflow_uuid='33930b26-2780-555f-8668-e56462846716',
    displayname='S06 加液调试',
)
def s06_加液调试(
    *,
    pump: int = 1,
    volume: int = 8,
):
    # unilab:node_uuid=b6568882-960a-539f-b70a-63194267b086
    addition = szlab_mixer_pump_device.run_solvent_addition(beaker_true_means_present=True, process=1, pump=pump, skip_level_check=False, skip_robot=True, volume=volume, volume_pump_1=1, volume_pump_2=1)
    return {}
