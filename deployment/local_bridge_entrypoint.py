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

from szlab_poly_studio.shape_library import material_shape_items
from unilabos.app.local_bridge import local_api, server
from unilabos.devices.generic_plc_macro import DeclarativePLCMacroDriver
from unilabos.runtime.profile_loader import LoadedProfile, load_profiles


def load_repository_profiles(
    paths: list[str | Path],
) -> dict[str, LoadedProfile]:
    driver_catalog: Mapping[str, Any] = {
        "generic_plc_macro": DeclarativePLCMacroDriver,
    }
    return load_profiles(paths, driver_catalog=driver_catalog)


def install_material_shape_route() -> None:
    """Backfill the package-owned shape route until Edge provides it natively."""

    original_create_app = local_api.create_app
    items = material_shape_items()

    def create_app_with_material_shapes(*args: Any, **kwargs: Any) -> Any:
        app = original_create_app(*args, **kwargs)
        if any(
            getattr(route, "path", None) == "/api/v1/material-shapes"
            for route in app.routes
        ):
            return app

        @app.get("/api/v1/material-shapes")
        async def api_v1_material_shapes() -> dict[str, Any]:
            return {
                "code": 0,
                "data": {"items": items},
                "message": "ok",
            }

        return app

    local_api.create_app = create_app_with_material_shapes


def main() -> None:
    server.load_profiles = load_repository_profiles
    install_material_shape_route()
    server.main()


if __name__ == "__main__":
    main()
