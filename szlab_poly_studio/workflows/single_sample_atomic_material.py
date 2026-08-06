from typing import Annotated, TypedDict
from pydantic import Field
from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import SzlabMixerPhotoShottingDevice
from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import SzlabMixerPipettingStationDevice
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import SzlabMixerMagneticStirrerDevice
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import SZLabS07SolidAdditionDevice
from szlab_poly_studio.devices.szlab_s08_cap_station.device import SZLabS08CapStationDevice
from unilabos.ros.nodes.presets.host_node import HostNode
from szlab_poly_studio.workflows.material_transfer import s_z_lab_标准物料转运
from szlab_poly_studio.resources.materials import beaker_500ml
from szlab_poly_studio.resources.materials import liquid_reagent_bottle_100ml
from szlab_poly_studio.resources.materials import pipette_tip
from szlab_poly_studio.resources.materials import powder_container
from szlab_poly_studio.resources.materials import sample_vial_250ml
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import MaterialFlowRole, device, group, material_source, parallel, resource_ref, workflow_definition


class SZLab单样品全流程物料感知Result(TypedDict):
    product_vial: Annotated[ResourceSlot, AllowedResourceTemplates(sample_vial_250ml)]
    used_beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]
    reagent_bottle: Annotated[ResourceSlot, AllowedResourceTemplates(liquid_reagent_bottle_100ml)]
    coarse_powder_cartridge: Annotated[ResourceSlot, AllowedResourceTemplates(powder_container)]
    fine_powder_cartridge: Annotated[ResourceSlot, AllowedResourceTemplates(powder_container)]
    tip: Annotated[ResourceSlot, AllowedResourceTemplates(pipette_tip)]
    photo_path: str
    inspection_result: str
    commanded_powder_mass_g: float
    message: str


szlab_mixer_photo_shotting_device: SzlabMixerPhotoShottingDevice = device('szlab_mixer_photoshotting')
szlab_mixer_pipetting_station_device: SzlabMixerPipettingStationDevice = device('szlab_mixer_pipetting_station')
szlab_mixer_pump_device: SzlabMixerPumpDevice = device('szlab_mixer_pump')
szlab_mixer_robot_device: SzlabMixerRobotDevice = device('szlab_mixer_robot')
szlab_mixer_magnetic_stirrer_device: SzlabMixerMagneticStirrerDevice = device('szlab_mixer_stirrer')
s_z_lab_s07_solid_addition_device: SZLabS07SolidAdditionDevice = device('szlab_s07_solid_addition')
s_z_lab_s08_cap_station_device: SZLabS08CapStationDevice = device('szlab_s08_cap_station')
host_node: HostNode = device('host_node')


@workflow_definition(
    workflow_uuid='6d9fb3e2-4dcb-5f23-93b4-74d1b6083393',
    displayname='SZLab 单样品全流程（物料感知）',
    description='把旧 38 动作原子 JSON 改写为 MaterialSource、ResourceSlot、标准机械臂复合转运、多物料加工与命名 Workflow output。',
)
def s_z_lab_单样品全流程_物料感知(
    *,
    reagent_bottle: Annotated[ResourceSlot, AllowedResourceTemplates(liquid_reagent_bottle_100ml)],
    tip: Annotated[ResourceSlot, AllowedResourceTemplates(pipette_tip)],
    solvent_pump_1: Annotated[ResourceSlot, AllowedResourceTemplates(liquid_reagent_bottle_100ml)],
    solvent_pump_2: Annotated[ResourceSlot, AllowedResourceTemplates(liquid_reagent_bottle_100ml)],
    sample_id: str = 'sample-001',
    target_powder_mass_g: Annotated[float, Field(ge=0.001, le=100)] = 1.0,
    volume_pump_1: Annotated[int, Field(ge=0)] = 10,
    volume_pump_2: Annotated[int, Field(ge=0)] = 10,
    pipette_volume_raw: Annotated[int, Field(ge=1)] = 5000,
) -> SZLab单样品全流程物料感知Result:
    # unilab:node_uuid=c6551edc-856a-55f8-91a3-d9c7243fb636
    source_beaker = material_source(resource_template=beaker_500ml, mode='existing', mount=resource_ref('s3_unused_beaker'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.PRIMARY_SAMPLE)
    # unilab:node_uuid=71e3add0-cc3b-5657-8763-2ce15d823077
    source_sample_vial = material_source(resource_template=sample_vial_250ml, mode='existing', mount=resource_ref('s3_unused_beaker'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.CONSUMABLE)
    # unilab:node_uuid=0164a018-80c0-52ac-9350-47e8b5cdec01
    source_coarse_powder = material_source(resource_template=powder_container, mode='existing', mount=resource_ref('powder_container_warehouse'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.REAGENT)
    # unilab:node_uuid=5f3ee9e8-6790-527b-80a8-40f4c5f51cbf
    source_fine_powder = material_source(resource_template=powder_container, mode='existing', mount=resource_ref('powder_container_warehouse'), material_uuid=None, site=None, slot_range=None, flow_role=MaterialFlowRole.REAGENT)
    # unilab:node_uuid=b46df2d0-42b8-5460-b192-aaf53537579e
    powder_inventory = s_z_lab_s07_solid_addition_device.scan_powder_cartridges(timeout=300.0)
    with parallel():
        # unilab:node_uuid=2a7a6669-e60b-4e45-a63d-7d4e79903241
        with group(name='烧杯搬到 S07 交接位'):
            # unilab:node_uuid=db81cbea-7f28-5a86-94a0-13864cfb1fa5
            beaker_at_s07 = s_z_lab_标准物料转运(resource=source_beaker, source_warehouse=resource_ref('s3_unused_beaker'), target_device='szlab_s07_solid_addition', target_warehouse=resource_ref('s07_process_warehouse'), source_site='L1B1', target_site='S0721')
        # unilab:node_uuid=32e8bd24-58cf-447f-a808-59c2d1ea5d4b
        with group(name='精注粉瓶搬到 S07 P02'):
            # unilab:node_uuid=a522d335-ccc7-5942-a7eb-669cfc6942a9
            prepared_fine = s_z_lab_s07_solid_addition_device.prepare_powder_cartridge_site(powder_cartridge=source_fine_powder, powder_site='P02', timeout=300.0)
            # unilab:node_uuid=3754171f-01a2-51b7-af0e-64512996226b
            fine_at_s07 = s_z_lab_标准物料转运(resource=prepared_fine.powder_cartridge, source_warehouse=resource_ref('powder_container_warehouse'), target_device='szlab_s07_solid_addition', target_warehouse=resource_ref('s07_process_warehouse'), source_site='L1C2', target_site='P02')
        # unilab:node_uuid=4ac465ac-9812-41a9-92bb-9cb6de47a222
        with group(name='粗注粉瓶搬到 S07 P01'):
            # unilab:node_uuid=671c77fc-56a4-5512-82f9-de6ce25d4e8a
            prepared_coarse = s_z_lab_s07_solid_addition_device.prepare_powder_cartridge_site(powder_cartridge=source_coarse_powder, powder_site='P01', timeout=300.0)
            # unilab:node_uuid=3f8eab79-f12d-52df-b66b-8a4efa04529d
            coarse_at_s07 = s_z_lab_标准物料转运(resource=prepared_coarse.powder_cartridge, source_warehouse=resource_ref('powder_container_warehouse'), target_device='szlab_s07_solid_addition', target_warehouse=resource_ref('s07_process_warehouse'), source_site='L1C1', target_site='P01')
    # unilab:node_uuid=64cae18e-a070-5ceb-bc09-997c53e35e1f
    dosed = s_z_lab_s07_solid_addition_device.dose_powder_with_two_materials(beaker=beaker_at_s07.resource, coarse_powder_cartridge=coarse_at_s07.resource, coarse_powder_site='P01', fine_powder_cartridge=fine_at_s07.resource, fine_powder_site='P02', params_json=None, recipe_name='default', target_mass_g=target_powder_mass_g, timeout=300.0)
    with parallel():
        # unilab:node_uuid=9e41d9a1-bb69-4798-9de5-55d3668a5ef6
        with group(name='烧杯在 S06 加溶剂并搬到 S09'):
            # unilab:node_uuid=618aaeda-ffba-5d74-b9f8-93366cd11e4b
            beaker_at_s06 = s_z_lab_标准物料转运(resource=dosed.beaker, source_warehouse=resource_ref('s07_process_warehouse'), target_device='szlab_mixer_pump', target_warehouse=resource_ref('s06_process_warehouse'), source_site='S0721', target_site='S061')
            # unilab:node_uuid=00e72600-5c9c-5afd-9c70-338d6eddc102
            added_solvents = szlab_mixer_pump_device.add_solvent_with_materials(beaker=beaker_at_s06.resource, beaker_true_means_present=True, skip_level_check=False, solvent_pump_1=solvent_pump_1, solvent_pump_2=solvent_pump_2, volume_pump_1=volume_pump_1, volume_pump_2=volume_pump_2)
            # unilab:node_uuid=96db2ac9-4cb9-5242-b1b7-63e81c416aa4
            beaker_at_s09 = s_z_lab_标准物料转运(resource=added_solvents.beaker, source_warehouse=resource_ref('s06_process_warehouse'), target_device='szlab_mixer_pipetting_station', target_warehouse=resource_ref('s09_process_warehouse'), source_site='S061', target_site='BEAKER1')
        # unilab:node_uuid=f473e32b-9dda-465c-9813-55996fe4b70a
        with group(name='液体试剂瓶开盖并搬到 S09'):
            # unilab:node_uuid=e01e23ce-72d2-5136-b849-60fa3fe2525f
            reagent_at_s08 = s_z_lab_标准物料转运(resource=reagent_bottle, source_warehouse=resource_ref('s10_liquid_reagent'), target_device='szlab_s08_cap_station', target_warehouse=resource_ref('s08_process_warehouse'), source_site='R1C1', target_site='S082')
            # unilab:node_uuid=38c2603a-0dac-5930-a26e-966138075939
            opened_reagent = s_z_lab_s08_cap_station_device.process_liquid_reagent_100ml_cap_with_material(container=reagent_at_s08.resource, operation='open', sample_id=sample_id, timeout=300.0)
            # unilab:node_uuid=c0a01cc2-507c-5d28-84bd-192079cd7d59
            reagent_at_s09 = s_z_lab_标准物料转运(resource=opened_reagent.container, source_warehouse=resource_ref('s08_process_warehouse'), target_device='szlab_mixer_pipetting_station', target_warehouse=resource_ref('s09_process_warehouse'), source_site='S082', target_site='REAGENT1')
    # unilab:node_uuid=c535cf80-22f3-5f92-9222-020d66f8b3ea
    pipetted = szlab_mixer_pipetting_station_device.add_liquid_with_materials(aspirate_volume=pipette_volume_raw, beaker=beaker_at_s09.resource, dispense_volume=pipette_volume_raw, liquid_bottle_index=1, reagent_bottle=reagent_at_s09.resource, skip_level_check=False, station=1, tip=tip, tip_box_index=1, tip_index=1, volume_unit='raw')
    # unilab:node_uuid=6ade06a7-f2e8-57f5-8d29-8124d303e43e
    beaker_at_s04 = s_z_lab_标准物料转运(resource=pipetted.beaker, source_warehouse=resource_ref('s09_process_warehouse'), target_device='szlab_mixer_stirrer', target_warehouse=resource_ref('s04_process_warehouse'), source_site='BEAKER1', target_site='S041')
    # unilab:node_uuid=ffa0066c-b9c2-5d37-aff3-bfac6481b01c
    stirred = szlab_mixer_magnetic_stirrer_device.stir_beaker(beaker=beaker_at_s04.resource, duration=30.0, mode=3, position=1, reset=False, safe_temperature=80, speed=300, temperature=25)
    with parallel():
        # unilab:node_uuid=7b70c8ab-b4d4-4dc2-b675-6b6f972b69a4
        with group(name='烧杯搬到 S05 并拍照'):
            # unilab:node_uuid=5aff8d44-869d-503b-85e1-abca3da3980b
            beaker_at_s05 = s_z_lab_标准物料转运(resource=stirred.beaker, source_warehouse=resource_ref('s04_process_warehouse'), target_device='szlab_mixer_photoshotting', target_warehouse=resource_ref('s05_process_warehouse'), source_site='S041', target_site='S051')
            # unilab:node_uuid=ea651e5f-bbdd-580c-a3ce-75ff7f30da7c
            inspected = szlab_mixer_photo_shotting_device.inspect_beaker(beaker=beaker_at_s05.resource, inspection_result='', photo_path='', sample_id=sample_id)
        # unilab:node_uuid=d2961527-c462-48d2-817d-8ba5e33ced54
        with group(name='样品瓶搬到 S08 并开盖'):
            # unilab:node_uuid=8eb012b4-f12a-5d61-a675-3bd68147ca85
            sample_vial_at_s08 = s_z_lab_标准物料转运(resource=source_sample_vial, source_warehouse=resource_ref('s3_unused_beaker'), target_device='szlab_s08_cap_station', target_warehouse=resource_ref('s08_process_warehouse'), source_site='L1A1', target_site='S081')
            # unilab:node_uuid=05fcfaa8-f511-519e-b29b-b6035086fd93
            opened_sample_vial = s_z_lab_s08_cap_station_device.process_sample_vial_250ml_cap_with_material(container=sample_vial_at_s08.resource, operation='open', sample_id=sample_id, timeout=300.0)
    # unilab:node_uuid=c3305a3e-c047-5c64-be13-18fd07c85436
    picked_for_pour = szlab_mixer_robot_device.pick_beaker(beaker=inspected.beaker, site='S051', warehouse=resource_ref('s05_process_warehouse'))
    # unilab:node_uuid=c50f7c2c-b4b6-5c3b-be91-25675bb0d842
    poured = szlab_mixer_robot_device.pour_beaker_into_vial(beaker=picked_for_pour.beaker, sample_vial=opened_sample_vial.container, sample_vial_site='S081')
    with parallel():
        # unilab:node_uuid=27553e30-29e1-4f01-a696-a66858a4c7d3
        with group(name='使用后烧杯回 S11'):
            # unilab:node_uuid=3f4d4079-8964-5414-803a-8dc4873498b5
            placed_used_beaker = szlab_mixer_robot_device.place(resource=poured.beaker, site='L1B1', warehouse=resource_ref('s11_used_beaker'))
            # unilab:node_uuid=99d2a553-bcaa-5a69-a302-953f28790fcd
            committed_used_beaker = host_node.transfer_resource(mount_resource=resource_ref('s11_used_beaker'), resource=placed_used_beaker.resource, site='L1B1', target_device='host_node')
        # unilab:node_uuid=dcfbef8f-83b3-43ee-b8d7-07de5c10cd66
        with group(name='S08 关闭成品样品瓶'):
            # unilab:node_uuid=f7a8bda7-0ebf-5752-9598-1ef2c7f90fe3
            closed_sample_vial = s_z_lab_s08_cap_station_device.process_sample_vial_250ml_cap_with_material(container=poured.sample_vial, operation='close', sample_id=sample_id, timeout=300.0)
    # unilab:node_uuid=8436dc02-a9f3-5286-9822-6e5d22ae4205
    product_vial_at_s11 = s_z_lab_标准物料转运(resource=closed_sample_vial.container, source_warehouse=resource_ref('s08_process_warehouse'), target_device='host_node', target_warehouse=resource_ref('s11_used_beaker'), source_site='S081', target_site='L1A1')
    return {'product_vial': poured.sample_vial, 'used_beaker': poured.beaker, 'reagent_bottle': pipetted.reagent_bottle, 'coarse_powder_cartridge': dosed.coarse_powder_cartridge, 'fine_powder_cartridge': dosed.fine_powder_cartridge, 'tip': pipetted.tip, 'photo_path': inspected.photo_path, 'inspection_result': inspected.inspection_result, 'commanded_powder_mass_g': dosed.commanded_mass_g, 'message': closed_sample_vial.message}
