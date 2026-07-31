# 本地验证记录

验证日期：2026-07-31（Asia/Shanghai）。

## 基线

- Uni-Lab-OS 本地联调提交：`0812ec90aab6b293d9088af48645d740a49392c8`
- uni-lab-fe 最新本地提交：`d734337f63da832c11d704013be0d80f98681116`
- 设备迁移来源：`styx/dev@d58a8c0d6de26b9de77161359bb627d75fa8e4e8`
- 模板与 schema：`Uni-Lab-Templates@5e44020e1020577b0c00ba196f82a7e434983b29`
- Python：`/home/changjunhan/.micromamba/envs/unilab/bin/python`，3.11.14
- Uni-Lab-OS CLI：0.11.3

## 自动验证

以下检查均通过：

- Ruff：`ruff check packages tests deployment/local_bridge_entrypoint.py`
- Pytest：20 项测试
- `unilab --check_mode --external_devices_only`：两套包全部通过
- Profile 加载：SZLab 78 个动作，AI4C 19 个动作，共 97 个本地动作
- Registry：9 个 SZLab 项目设备、2 个 AI4C 项目设备、15 个 SZLab 资源
- Python 工作流：13 个源码全部通过 AST 编译；12 个 local UI preset 全部有迁移映射
- Schema：Profile v1 与 device-template v2 的仓库副本和模板提交逐字节一致
- Wheel：两个包均可构建，且包含 Profile、工作流和 CSV 数据
- 包边界：SZLab 与 AI4C 无交叉导入，可分别 check、build 和启动本地 bridge；独立 bridge
  分别暴露 78/19 个动作，AI4C 图只包含自己的 2 个对象

核心复现命令：

```bash
export UNILAB_PYTHON=/home/changjunhan/.micromamba/envs/unilab/bin/python
export PYTHONPATH="../Uni-Lab-OS:packages/szlab_poly_studio:packages/ai4c_robot"

"$UNILAB_PYTHON" -m ruff check packages tests
"$UNILAB_PYTHON" -m pytest -q
UNILAB_COMMAND=/home/changjunhan/.micromamba/envs/unilab/bin/unilab \
  ./scripts/check-packages.sh
"$UNILAB_PYTHON" -m pip wheel --no-deps --no-build-isolation \
  -w /tmp/szlab-wheels packages/szlab_poly_studio packages/ai4c_robot
```

## OS 与最新前端联调

authoring bridge 以 OfflineOS 模式加载两套 Profile 和 `deployment/graphs/local-debug.json`。验证结果：

- `/health` 正常；
- `/api/v1/materials` 返回 24 个图中实例；
- `/api/v1/authoring/actions` 返回 97 个动作；
- S04 三节点 Python 工作流经 HTTP 编译、Canonical v2 校验和 revision 保存成功；
- offline runtime run 完成，3 个节点全部成功，22 个事件序号单调；
- 最新 `uni-lab-fe` 的 typecheck、67 项测试和 production Web build 全部通过；
- 浏览器从前端 origin 访问 bridge，工作流/物料 UI 可见，并读取 24 个物料实例、97 个动作；
  浏览器端编译 S04 工作流无诊断、无控制台错误。

拆包后的 SZLab 定向 E2E 进一步使用只含 SZLab 的 graph/Profile，验证两页共 126 个物料聚合、
14 条设备包外形声明、S04 三节点 Python 工作流、2D 与 2.5D 视图；并断言 S04 磁搅节点使用
`stirrer_rack`、试剂瓶使用 `capped_reagent_bottle` 外形而不是默认包围盒，同时覆盖 2.5D
缩放/适应全部控制。截图见 `docs/E2E_SCREENSHOTS.md`。

全工作流 E2E 自动发现并逐一验证两个包中的 13 个 Python 源码（SZLab 12、AI4C 1），每个均
经直接 API 编译、前端按钮编译和 Canonical 校验后截图；总览见
`docs/ALL_WORKFLOW_SCREENSHOTS.md`。

真实 PLC、机械臂、相机和执行机构未在这轮自动验证中上电。本地图对所有直连 OPC UA 设备使用
`auto_connect: false`；真机验收项见 `docs/HARDWARE_BRINGUP.md`。
