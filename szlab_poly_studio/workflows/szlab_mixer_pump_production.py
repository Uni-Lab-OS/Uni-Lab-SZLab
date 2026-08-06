from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_pump_device: SzlabMixerPumpDevice = device('szlab_mixer_pump')


@workflow_definition(
    workflow_uuid='127cf68e-43b3-58ab-932f-984f2b57019e',
    displayname='S06 加液生产流程',
)
def s06_加液生产流程(
    *,
    pump: int = 1,
    volume: int = 8,
) -> None:
    # unilab:node_uuid=958e8abc-1cb6-5d75-b1cb-eaf0524b3a54
    addition = szlab_mixer_pump_device.run_solvent_addition(beaker_true_means_present=True, process=1, pump=pump, skip_level_check=False, skip_robot=True, volume=volume, volume_pump_1=1, volume_pump_2=1)
