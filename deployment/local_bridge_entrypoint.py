"""Run the local bridge with only the driver catalog required by this repo.

Uni-Lab environments may contain unrelated editable driver plugins. Importing
every global ``unilabos.drivers`` entry point makes an isolated SZLab/AI4C
debug session depend on those plugins' import health. Both profiles in this
repository use only ``generic_plc_macro``, so the local bridge pins that exact
catalog while leaving the normal Uni-Lab-OS launcher unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from unilabos.app.local_bridge import server
from unilabos.devices.generic_plc_macro import DeclarativePLCMacroDriver
from unilabos.runtime.profile_loader import LoadedProfile, load_profiles


def load_repository_profiles(
    paths: list[str | Path],
) -> dict[str, LoadedProfile]:
    driver_catalog: Mapping[str, Any] = {
        "generic_plc_macro": DeclarativePLCMacroDriver,
    }
    return load_profiles(paths, driver_catalog=driver_catalog)


def main() -> None:
    server.load_profiles = load_repository_profiles
    server.main()


if __name__ == "__main__":
    main()
