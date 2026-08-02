from unilabos.workflow.authoring import device, workflow_definition

from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
    SzlabMixerPipettingStationDevice,
)

szlab_mixer_pipetting_station: SzlabMixerPipettingStationDevice = device("szlab_mixer_pipetting_station")


@workflow_definition(
    workflow_uuid="d176a938-5e34-511b-9e28-68540833559b",
    displayname="S09 移液调试",
)
def szlab_s09_pipetting_workflow(
    *,
    liquid_bottle_index: int = 1,
    volume_ul: float = 100.0,
) -> None:
    # unilab:node_uuid=78f5737a-694c-56fd-b6dd-fcd35a6dcedc
    prepared = szlab_mixer_pipetting_station.prepare_liquid_station()  # noqa: F841
    # unilab:node_uuid=b316e4f0-8cf8-5457-a723-7b67ad5b8758
    bound = szlab_mixer_pipetting_station.bind_sample_to_station(  # noqa: F841
        sample_id="debug-sample",
    )
    # unilab:node_uuid=7a6cb117-2f8a-5696-93f3-83d2d348da98
    added = szlab_mixer_pipetting_station.add_liquid(  # noqa: F841
        liquid_bottle_index=liquid_bottle_index,
        aspirate_volume=volume_ul,
        dispense_volume=volume_ul,
        tip_box_index=1,
        tip_index=1,
        station=1,
        volume_unit="ul",
        skip_level_check=False,
    )
    # unilab:node_uuid=61b329f0-4476-555c-8286-bf8bf29dd824
    released = szlab_mixer_pipetting_station.release_station()  # noqa: F841
