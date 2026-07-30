"""Declare the SZLab polymer-studio model bundle for Uni-Lab-OS discovery.

Edge discovers this via the ``unilabos.model_bundles`` entry point.  The
provider only describes where the manifests live; it must not open hardware
or start threads.

``manifest`` 是 3D 模型清单，``shape_manifest`` 是 2.5D 外形清单——两者都是本
设备包自己的资产，前端按需读取，不在前端内写死。
"""

from __future__ import annotations


def get_model_bundle() -> dict[str, str]:
    return {
        "package": "szlab_poly_studio",
        "manifest": "model_manifest.yaml",
        "shape_manifest": "shape_manifest.yaml",
    }
