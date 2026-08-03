# SZLab 根单包迁移验证

## 环境

在可导入相邻 `../Uni-Lab-OS` 的 Python 3.11 环境中执行。该 OS 必须包含 A1 typed
Action contract、`unilabos.registry.annotations` 和 I1 Workflow input/output integration：

```bash
export PYTHONPATH="../Uni-Lab-OS:$(pwd)${PYTHONPATH:+:${PYTHONPATH}}"
python -m pytest
./scripts/check-package.sh
./scripts/build-package.sh
```

## 验证范围

自动测试覆盖：

- 仓库不存在 `packages/` 层，distribution/import package 身份对齐；
- Catalog 发现 9 个 SZLab 设备和 14 个 SZLab 资源；
- 两个部署 Graph 的全部 class 都使用 `community.szlab_poly_studio.*` 并解析到 Catalog；
- 连接参数与物料拓扑只存在于 Graph，仓库不包含运行时 Profile；
- 13 个生产 Python 工作流可进入 Package Catalog，其中 S06 材料参考链验证 Action 级
  `ResourceSlot`、模板限制、命名 output 与线性绑定；
- 所有 decorator-bound `models/shape.yml` 路径存在且位于包内；
- 拆分后的外形仍覆盖设备、warehouse 和物料 category；
- Graph 中只有主 PLC 拥有直连配置，业务设备通过 `plc_device_id` 复用它；
- wheel 包含 CSV、JSON、工作流和模型 YAML，并嵌入 canonical Catalog；
- 未改变启动脚本的 755 权限。

## 后续模型验收

当前 Catalog、`--workspace`、clean-wheel parity 与 Shape 资产读取已覆盖。第一套真实 Xacro
进入仓库后，仍需补充 Web、kinematics、collision 与 `mesh_path` 的实物模型闭环。
