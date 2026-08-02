from typing import TYPE_CHECKING

__all__ = [
    "SZLabPolyPLCDevice",
    "SZLabPolyStudioDeck",
    "SZLabS07SolidAdditionDevice",
    "SZLabS08CapStationDevice",
    "S1Workstation",
    "SzlabMixerRobotDevice",
    "SzlabMixerPumpDevice",
    "SzlabMixerPhotoShottingDevice",
    "SzlabMixerMagneticStirrerDevice",
    "SzlabMixerPipettingStationDevice",
    "beaker_500ml",
    "liquid_reagent_bottle_100ml",
    "pipette_tip",
    "powder_container",
    "sample_vial_250ml",
    "sample_vial_500ml",
    "powder_container_placeholder_warehouse",
    "s1_loading_buffer_warehouse",
    "s2_tip_placeholder_warehouse",
    "s3_unused_beaker_warehouse",
    "s3_unused_sample_vial_warehouse",
    "s10_liquid_reagent_placeholder_warehouse",
    "s11_used_beaker_warehouse",
    "s11_used_sample_vial_warehouse",
    "s04_process_warehouse",
    "s05_process_warehouse",
    "s06_process_warehouse",
    "s07_process_warehouse",
]

if TYPE_CHECKING:
    from szlab_poly_studio.devices.s1_workstation import S1Workstation
    from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import SzlabMixerPhotoShottingDevice
    from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
        SzlabMixerPipettingStationDevice,
    )
    from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
    from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
    from szlab_poly_studio.devices.szlab_mixer_stirrer.device import SzlabMixerMagneticStirrerDevice
    from szlab_poly_studio.devices.szlab_poly_plc.device import SZLabPolyPLCDevice
    from szlab_poly_studio.devices.szlab_s07_solid_addition.device import SZLabS07SolidAdditionDevice
    from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
        SZLabS08CapStationDevice,
    )
    from szlab_poly_studio.resources.decks import SZLabPolyStudioDeck
    from szlab_poly_studio.resources.warehouses import (
        powder_container_placeholder_warehouse,
        s1_loading_buffer_warehouse,
        s2_tip_placeholder_warehouse,
        s3_unused_beaker_warehouse,
        s3_unused_sample_vial_warehouse,
        s10_liquid_reagent_placeholder_warehouse,
        s11_used_beaker_warehouse,
        s11_used_sample_vial_warehouse,
        s04_process_warehouse,
        s05_process_warehouse,
        s06_process_warehouse,
        s07_process_warehouse,
    )


def __getattr__(name: str):
    if name == "SZLabPolyPLCDevice":
        from szlab_poly_studio.devices.szlab_poly_plc.device import SZLabPolyPLCDevice

        return SZLabPolyPLCDevice
    if name == "SZLabPolyStudioDeck":
        from szlab_poly_studio.resources.decks import SZLabPolyStudioDeck

        return SZLabPolyStudioDeck
    if name == "S1Workstation":
        from szlab_poly_studio.devices.s1_workstation import S1Workstation

        return S1Workstation
    if name == "SZLabS07SolidAdditionDevice":
        from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
            SZLabS07SolidAdditionDevice,
        )

        return SZLabS07SolidAdditionDevice
    if name == "SZLabS08CapStationDevice":
        from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
            SZLabS08CapStationDevice,
        )

        return SZLabS08CapStationDevice
    if name == "SzlabMixerRobotDevice":
        from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice

        return SzlabMixerRobotDevice
    if name == "SzlabMixerPumpDevice":
        from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice

        return SzlabMixerPumpDevice
    if name == "SzlabMixerPhotoShottingDevice":
        from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import SzlabMixerPhotoShottingDevice

        return SzlabMixerPhotoShottingDevice
    if name == "SzlabMixerMagneticStirrerDevice":
        from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
            SzlabMixerMagneticStirrerDevice,
        )

        return SzlabMixerMagneticStirrerDevice
    if name == "SzlabMixerPipettingStationDevice":
        from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
            SzlabMixerPipettingStationDevice,
        )

        return SzlabMixerPipettingStationDevice
    if name in {
        "beaker_500ml",
        "liquid_reagent_bottle_100ml",
        "pipette_tip",
        "powder_container",
        "sample_vial_250ml",
        "sample_vial_500ml",
    }:
        from szlab_poly_studio.resources import materials

        return getattr(materials, name)
    if name in {
        "powder_container_placeholder_warehouse",
        "s1_loading_buffer_warehouse",
        "s2_tip_placeholder_warehouse",
        "s3_unused_beaker_warehouse",
        "s3_unused_sample_vial_warehouse",
        "s10_liquid_reagent_placeholder_warehouse",
        "s11_used_beaker_warehouse",
        "s11_used_sample_vial_warehouse",
        "s04_process_warehouse",
        "s05_process_warehouse",
        "s06_process_warehouse",
        "s07_process_warehouse",
    }:
        from szlab_poly_studio.resources import warehouses

        return getattr(warehouses, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
