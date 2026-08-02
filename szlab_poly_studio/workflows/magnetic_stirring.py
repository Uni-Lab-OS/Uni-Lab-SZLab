from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)

szlab_mixer_stirrer: SzlabMixerMagneticStirrerDevice = device("szlab_mixer_stirrer")


@workflow_definition(
    workflow_uuid="67da810c-34f6-59c6-94ba-7e73dcc06207",
    displayname="S04 磁搅单工位调试",
)
def szlab_magnetic_stirring_workflow(
    *,
    position: int = 1,
    speed: float = 300.0,
    temperature: float = 25.0,
    duration: float = 30.0,
) -> None:
    # unilab:node_uuid=194ed35e-9c30-5a2d-9da5-9e70ff3992e4
    stirring = szlab_mixer_stirrer.run_stirring(  # noqa: F841
        position=position,
        mode=3,
        speed=speed,
        temperature=temperature,
        duration=duration,
        safe_temperature=80.0,
        reset=False,
    )
