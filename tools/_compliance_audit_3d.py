"""Audit SZLab/OS/FE against 设备包3D模型存储规范 (Issue #147 direction)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"f:\GitHub\new\Uni-Lab-Core\Uni-Lab-SZLab")
PKG = ROOT / "szlab_poly_studio"
OS_ROOT = Path(r"f:\GitHub\new\Uni-Lab-Core\Uni-Lab-OS")
FE_ROOT = Path(r"f:\GitHub\new\Uni-Lab-Core\uni-lab-fe")

issues: list[tuple[str, str, str]] = []


def add(sev: str, msg: str, where: str) -> None:
    issues.append((sev, msg, where))


# 1) packages/ middle layer forbidden
if (ROOT / "packages").exists():
    add("CRITICAL", "禁止 packages/ 中间层", "Uni-Lab-SZLab/packages")

# 2) package-level second discovery
for name in (
    "model_manifest.yaml",
    "model_manifest.yml",
    "shape_manifest.yaml",
    "shape_manifest.yml",
):
    for p in ROOT.rglob(name):
        if any(x in p.parts for x in (".git", "node_modules", ".venv")):
            continue
        add("CRITICAL", "禁止包级第二套模型发现配置", str(p.relative_to(ROOT)))

# 3) absolute paths in xacro
for p in PKG.rglob("*.xacro"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    rel = str(p.relative_to(ROOT))
    if re.search(r'filename="/(?!\$\{)', text) or re.search(
        r"filename='/(?!\$\{)", text
    ):
        add("CRITICAL", "Xacro 含绝对路径 filename", rel)
    if re.search(r"[A-Za-z]:\\|/Users/|/home/", text):
        add("CRITICAL", "Xacro 含本机绝对路径", rel)
    if "meshes/" in text and "${mesh_path}" not in text:
        add("WARN", "含 meshes/ 但未见 ${mesh_path} 注入写法", rel)

# 4) macro_device.xacro duplicates
for p in PKG.rglob("macro_device.xacro"):
    add(
        "WARN",
        "存在 macro_device.xacro 副本（规范入口应为 device.xacro / resource.xacro）",
        str(p.relative_to(ROOT)),
    )

# 5) devices with device.xacro must bind format=xacro
for d in (PKG / "devices").iterdir():
    if not d.is_dir():
        continue
    xacro = d / "models" / "device.xacro"
    dev_py = d / "device.py"
    if xacro.exists() and dev_py.exists():
        t = dev_py.read_text(encoding="utf-8", errors="ignore")
        if '"format": "xacro"' not in t and "'format': 'xacro'" not in t:
            add(
                "CRITICAL",
                "有 device.xacro 但装饰器未绑定 format=xacro",
                str(dev_py.relative_to(ROOT)),
            )

# 6) resolve model.entry paths for devices
entry_re = re.compile(r'"entry"\s*:\s*"([^"]+)"')
for py in (PKG / "devices").rglob("device.py"):
    text = py.read_text(encoding="utf-8", errors="ignore")
    if '"format": "xacro"' not in text:
        continue
    for m in entry_re.finditer(text):
        entry = m.group(1)
        if entry.endswith("shape.yml"):
            continue
        if not (py.parent / entry).exists():
            add(
                "CRITICAL",
                f"装饰器 entry 不存在: {entry}",
                str(py.relative_to(ROOT)),
            )

# materials.py resource entries are package-relative under resources/
materials = PKG / "resources" / "materials.py"
if materials.exists():
    text = materials.read_text(encoding="utf-8", errors="ignore")
    for m in entry_re.finditer(text):
        entry = m.group(1)
        if "shape.yml" in entry:
            # shape entries in materials often omit resources/ prefix quirks
            p1 = PKG / "resources" / entry
            p2 = materials.parent / entry
            if not p1.exists() and not p2.exists():
                # tip_box may only have shape
                if not (PKG / "resources" / entry.split("/")[0]).exists():
                    add(
                        "WARN",
                        f"materials entry 可能缺失: {entry}",
                        "resources/materials.py",
                    )
            continue
        if entry.endswith(".xacro"):
            p = PKG / "resources" / entry
            if not p.exists():
                add(
                    "CRITICAL",
                    f"materials xacro entry 不存在: {entry}",
                    "resources/materials.py",
                )

# 7) pyproject package-data
pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
for n in ("**/*.xacro", "**/*.stl", "**/*.yml", "**/*.urdf"):
    if n not in pp:
        add("CRITICAL", f"pyproject package-data 缺少 {n}", "pyproject.toml")

# 8) .yaml under models/
for p in PKG.rglob("models"):
    if not p.is_dir():
        continue
    for y in p.rglob("*.yaml"):
        add(
            "WARN",
            "模型目录使用 .yaml（兼容期规范要求用 .yml）",
            str(y.relative_to(ROOT)),
        )

# 9) S09 referenced meshes exist
px = PKG / "devices" / "szlab_mixer_pipetting_station" / "models" / "device.xacro"
if px.exists():
    for mesh in re.findall(
        r"meshes/([A-Za-z0-9_\-\.]+)",
        px.read_text(encoding="utf-8", errors="ignore"),
    ):
        if not (px.parent / "meshes" / mesh).exists():
            add("CRITICAL", f"S09 xacro 引用缺失 mesh: {mesh}", str(px.relative_to(ROOT)))

# 10) OS dual channel
mm = OS_ROOT / "unilabos" / "app" / "local_bridge" / "material_models.py"
if mm.exists():
    t = mm.read_text(encoding="utf-8", errors="ignore")
    if "register_catalog" not in t:
        add(
            "CRITICAL",
            "OS 无 PackageCatalog.register_catalog（Issue #147 方向未完整）",
            str(mm),
        )
    if "model_bundles" in t:
        add(
            "WARN",
            "OS 仍保留 model_bundles（SZLab 规范禁止以此作为包发现协议）",
            str(mm),
        )
    if not (OS_ROOT / "unilabos" / "packages" / "catalog.py").exists():
        add(
            "CRITICAL",
            "缺少 unilabos/packages/catalog.py（PackageCatalog 未入库/未跟踪）",
            "Uni-Lab-OS/unilabos/packages/",
        )

# 11) SZLab bridge shape override
ep = ROOT / "deployment" / "local_bridge_entrypoint.py"
if ep.exists() and "material-shapes" in ep.read_text(encoding="utf-8", errors="ignore"):
    add(
        "WARN",
        "local_bridge 仍手工覆写 /api/v1/material-shapes（与 Catalog 通道并行）",
        str(ep.relative_to(ROOT)),
    )

# 12) FE must support macro + meshDir + origin
fe_schema = (
    FE_ROOT
    / "packages"
    / "pascal-lab-plugin"
    / "src"
    / "schema.ts"
)
if fe_schema.exists():
    t = fe_schema.read_text(encoding="utf-8", errors="ignore")
    for key in ("macro", "origin", "meshDir"):
        if key not in t and (key != "meshDir" or "meshDir" not in t and "mesh_dir" not in t):
            if key == "meshDir" and ("meshDir" in t or "mesh_dir" in t):
                continue
            if key not in t:
                add("WARN", f"FE schema 可能缺少字段 {key}", str(fe_schema))

# 13) VALIDATION: unilab --workspace --check_mode not available yet
# Flag as gap from VALIDATION.md
add(
    "GAP",
    "VALIDATION.md：OS 尚未正式交付 unilab --workspace/--check_mode 闭环（文档称 Issue #147）",
    "docs/VALIDATION.md",
)

print(f"ISSUES={len(issues)}")
for sev, msg, where in issues:
    print(f"[{sev}]\t{msg}\t|\t{where}")
