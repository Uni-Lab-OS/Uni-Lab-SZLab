from szlab_poly_studio.devices.szlab_s08_cap_station.device import SZLabS08CapStationDevice
from unilabos.workflow.authoring import device, workflow_definition


s_z_lab_s08_cap_station_device: SZLabS08CapStationDevice = device('szlab_s08_cap_station')


@workflow_definition(
    workflow_uuid='230df44a-c725-551d-b43b-303ab5bd90ea',
    displayname='S08 开关盖联调',
)
def s08_开关盖联调():
    # unilab:node_uuid=b50cb6c7-539b-5b0c-8a02-61037a1fb3bc
    opened = s_z_lab_s08_cap_station_device.process_cap_with_sample_parts(operation='open', sample_id_1=101, sample_id_2=102, sample_id_3=103, timeout=300.0, vial_type='liquid_100ml')
    # unilab:node_uuid=6baa8854-31d0-55ac-8d48-9f1fb8dedfa0
    closed = s_z_lab_s08_cap_station_device.process_cap_with_sample_parts(operation='close', sample_id_1=101, sample_id_2=102, sample_id_3=103, timeout=300.0, vial_type='liquid_100ml')
    return {}

