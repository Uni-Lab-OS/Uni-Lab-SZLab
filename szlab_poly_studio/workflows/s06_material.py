# 以 500 mL 烧杯 ResourceSlot 为主线的 S06 单工作流。

from typing import Annotated, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.resources.materials import beaker_500ml

szlab_mixer_robot: SzlabMixerRobotDevice = device("szlab_mixer_robot")
szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")


class S06MaterialWorkflowResult(TypedDict):
    beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
        Field(description="完成 S06 加液并被取回的 500 mL 烧杯"),
    ]
    addition_message: str


@workflow_definition(
    workflow_uuid="f372fd2d-447e-5f97-85e4-f90628e9f472",
    displayname="S06 材料感知加液",
    description="从 S03 取烧杯、放入 S06 加液，再从 S06 取回。",
)
def szlab_material_s06_workflow(
    *,
    beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
        Field(description="当前位于 S03、等待进入 S06 的 500 mL 烧杯"),
    ],
    pump: int = 1,
    volume: int = 8,
) -> S06MaterialWorkflowResult:
    # unilab:node_uuid=79839eb7-f30d-5251-b802-90631d819fff
    picked = szlab_mixer_robot.pick_beaker_from_s03(
        beaker=beaker,
        product_type=1,
        position="1-1",
    )
    # unilab:node_uuid=e357c916-fb2d-5e5c-bea5-7eb5e69def5c
    placed = szlab_mixer_robot.place_beaker_to_s06(
        beaker=picked.beaker,
    )
    # unilab:node_uuid=fd5fc6bf-a26b-54af-8bb0-68fd377a7394
    addition = szlab_mixer_pump.add_solvent_to_beaker(
        beaker=placed.beaker,
        pump=pump,
        volume=volume,
        skip_level_check=False,
        beaker_true_means_present=True,
    )
    # unilab:node_uuid=799e7e12-7147-58ce-8924-873406b1dcb2
    picked_after_addition = szlab_mixer_robot.pick_beaker_from_s06(
        beaker=addition.beaker,
    )
    return {
        "beaker": picked_after_addition.beaker,
        "addition_message": addition.message,
    }
