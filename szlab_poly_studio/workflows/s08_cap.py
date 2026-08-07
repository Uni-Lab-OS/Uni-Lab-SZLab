from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
    SZLabS08CapStationDevice,
)

szlab_s08_cap_station: SZLabS08CapStationDevice = device("szlab_s08_cap_station")


@workflow_definition(
    workflow_uuid="230df44a-c725-551d-b43b-303ab5bd90ea",
    displayname="S08 开关盖联调",
)
def s08_cap_workflow() -> None:
    # unilab:node_uuid=b50cb6c7-539b-5b0c-8a02-61037a1fb3bc
    opened = szlab_s08_cap_station.process_cap_with_sample_parts(  # noqa: F841
        operation="open",
        vial_type="liquid_100ml",
        sample_id_1=101,
        sample_id_2=102,
        sample_id_3=103,
        timeout=300.0,
    )
    # unilab:node_uuid=6baa8854-31d0-55ac-8d48-9f1fb8dedfa0
    closed = szlab_s08_cap_station.process_cap_with_sample_parts(  # noqa: F841
        operation="close",
        vial_type="liquid_100ml",
        sample_id_1=101,
        sample_id_2=102,
        sample_id_3=103,
        timeout=300.0,
    )
