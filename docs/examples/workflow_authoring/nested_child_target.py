"""C1 target only：当前 OS 尚不编译 imported subworkflow。"""

from typing import Annotated, TypedDict

from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.resources.materials import beaker_500ml

pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


class ChildResult(TypedDict):
    beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
    ]
    message: str


@workflow_definition(
    workflow_uuid="2538dd57-e0ec-5dd8-8a19-d21a53e31716",
    displayname="S06 子流程：烧杯加液",
    composition_allow_transparent=False,
)
def prepare_beaker(
    *,
    beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
    ],
    volume: int = 8,
) -> ChildResult:
    added = pump.add_solvent_to_beaker(
        beaker=beaker,
        pump=1,
        volume=volume,
    )
    return {"beaker": added.beaker, "message": added.message}
