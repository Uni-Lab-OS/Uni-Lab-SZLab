# SZLab 根单包迁移验证

## 环境

在可导入相邻 `../Uni-Lab-OS` 的 Python 3.11 环境中执行：

```bash
export PYTHONPATH="../Uni-Lab-OS:$(pwd)${PYTHONPATH:+:${PYTHONPATH}}"
python -m pytest
./scripts/check-package.sh
./scripts/build-package.sh
```

## 验证范围

自动测试覆盖：

- 仓库不存在 `packages/` 层，distribution/import package 身份对齐；
- AST Registry 发现 9 个 SZLab 设备和 14 个 SZLab 资源；
- Profile 与 device spec 位于 `szlab_poly_studio/profiles/default/` 且自包含；
- 12 个生产 Python 工作流可编译为 Canonical v2；
- 所有 decorator-bound `models/shape.yml` 路径存在且位于包内；
- 拆分后的外形仍覆盖设备、warehouse 和物料 category；
- Graph 中只有主 PLC 拥有直连配置，业务设备通过 `plc_device_id` 复用它；
- wheel 包含 Profile、CSV、JSON 和模型 YAML；
- 未改变启动脚本的 755 权限。

## 尚未覆盖的跨仓验收

当前 Uni-Lab-OS 尚未完成 Issue #147 的 PackageCatalogCompiler 和 `--workspace`。因此以下项目
必须在 OS delivery 后补充，不能由本仓库的兼容测试代替：

- `unilab --workspace . --check_mode`；
- workspace 与 clean-wheel Catalog 完全一致；
- Edge 对 decorator-bound Xacro/mesh 的安全资产 API；
- 第一套真实 Xacro 的 Web、kinematics、collision 和 `mesh_path` 闭环。
