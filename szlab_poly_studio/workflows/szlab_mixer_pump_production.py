from unilabos.workflow.authoring import device, workflow_definition, workflow_output

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice

szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


@workflow_definition(
    workflow_uuid="127cf68e-43b3-58ab-932f-984f2b57019e",
    displayname="S06 加液生产流程",
)
def szlab_mixer_pump_production(*, pump: int = 1, volume: int = 8):
    # unilab:node_uuid=958e8abc-1cb6-5d75-b1cb-eaf0524b3a54
    addition = szlab_mixer_pump.run_solvent_addition(  # noqa: F841
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
    return workflow_output()
