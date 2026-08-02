"""C1 target only：MaterialSource output → child input → parent output。"""

from typing import Annotated, TypedDict

from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import (
    MaterialFlowRole,
    material_source,
    resource_ref,
    workflow_definition,
)

from szlab_poly_studio.resources.materials import beaker_500ml

from .nested_child_target import prepare_beaker


class ParentResult(TypedDict):
    sample: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
    ]
    message: str


@workflow_definition(
    workflow_uuid="2fa01cb7-8aff-5438-92ce-45c0babe5d5f",
    displayname="SZLab 单样品复合流程",
)
def single_sample(*, volume: int = 8) -> ParentResult:
    source_beaker = material_source(
        resource_template=beaker_500ml,
        mode="existing",
        mount=resource_ref("<S03-mount-material-uuid>"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.PRIMARY_SAMPLE,
    )
    prepared = prepare_beaker(beaker=source_beaker, volume=volume)
    return {"sample": prepared.beaker, "message": prepared.message}
