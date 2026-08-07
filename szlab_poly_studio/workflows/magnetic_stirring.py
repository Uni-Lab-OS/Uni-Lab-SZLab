from szlab_poly_studio.devices.szlab_mixer_stirrer.device import SzlabMixerMagneticStirrerDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_magnetic_stirrer_device: SzlabMixerMagneticStirrerDevice = device('szlab_mixer_stirrer')


@workflow_definition(
    workflow_uuid='67da810c-34f6-59c6-94ba-7e73dcc06207',
    displayname='S04 磁搅单工位调试',
)
def s04_磁搅单工位调试(
    *,
    position: int = 1,
    speed: int = 300,
    temperature: int = 25,
    duration: float = 30.0,
):
    # unilab:node_uuid=194ed35e-9c30-5a2d-9da5-9e70ff3992e4
    stirring = szlab_mixer_magnetic_stirrer_device.run_stirring(duration=duration, mode=3, position=position, reset=False, safe_temperature=80.0, speed=speed, temperature=temperature)
    return {}

