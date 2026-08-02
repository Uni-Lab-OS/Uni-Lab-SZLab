from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice

szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


@workflow_definition(
    workflow_uuid="33930b26-2780-555f-8668-e56462846716",
    displayname="S06 加液调试",
)
def szlab_mixer_workflow(*, pump: int = 1, volume: float = 8.0) -> None:
    # unilab:node_uuid=b6568882-960a-539f-b70a-63194267b086
    addition = szlab_mixer_pump.run_solvent_addition(  # noqa: F841
        pump=pump,
        volume=volume,
        skip_level_check=False,
        skip_robot=True,
        beaker_true_means_present=True,
    )
