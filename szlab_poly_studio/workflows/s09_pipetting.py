from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import SzlabMixerPipettingStationDevice
from unilabos.workflow.authoring import device, workflow_definition


szlab_mixer_pipetting_station_device: SzlabMixerPipettingStationDevice = device('szlab_mixer_pipetting_station')


@workflow_definition(
    workflow_uuid='d176a938-5e34-511b-9e28-68540833559b',
    displayname='S09 移液调试',
)
def s09_移液调试(
    *,
    liquid_bottle_index: int = 1,
    volume_ul: int = 100,
) -> None:
    # unilab:node_uuid=78f5737a-694c-56fd-b6dd-fcd35a6dcedc
    prepared = szlab_mixer_pipetting_station_device.prepare_liquid_station()
    # unilab:node_uuid=b316e4f0-8cf8-5457-a723-7b67ad5b8758
    bound = szlab_mixer_pipetting_station_device.bind_sample_to_station(sample_id='debug-sample')
    # unilab:node_uuid=7a6cb117-2f8a-5696-93f3-83d2d348da98
    added = szlab_mixer_pipetting_station_device.add_liquid(S09液体瓶1剩余液量=None, S09液体瓶2剩余液量=None, S09液体瓶3剩余液量=None, S09液体瓶4剩余液量=None, S09液体瓶5剩余液量=None, aspirate_volume=volume_ul, dispense_volume=volume_ul, liquid_bottle_index=liquid_bottle_index, release_tip_box_index=2, skip_level_check=False, station=1, take_tip_box_index=1, tip_box_index=1, tip_index=1, volume_unit='ul')
    # unilab:node_uuid=61b329f0-4476-555c-8286-bf8bf29dd824
    released = szlab_mixer_pipetting_station_device.release_station()
