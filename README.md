# Uni-Lab SZLab Poly Studio

SZLab 聚合物工作站领域设备包。仓库根同时是 Python distribution root 和目标
Uni-Lab-OS workspace root；根目录只构建一个 distribution `szlab-poly-studio`，唯一常规
顶层 import package 是 `szlab_poly_studio`。

AI4C 已从本仓库迁出到同级的 `../Uni-Lab-AI4C/`，两边可以独立安装、测试、构建和发布。

## 目录合同

```text
Uni-Lab-SZLab/
├── pyproject.toml
├── szlab_poly_studio/
│   ├── devices/<device_id>/
│   │   ├── device.py
│   │   └── models/
│   ├── resources/
│   ├── workflows/
│   └── common/
├── deployment/
├── tests/
├── docs/
├── scripts/
└── migration/
```

没有 `packages/` 中间层，也没有独立的模型 entry-point 协议。设备、资源和工作流由各自装饰器
定义；模型元数据写在同一个 `@device` 或 `@resource` 上。设备专属资产放在
`devices/<device_id>/models/`，资源专属资产放在 `resources/<resource_id>/models/`，声明中
的 `entry` 相对装饰器所在 Python 文件解析。

当前仓库中的 2.5D 外形已按归属拆成各目录的 `models/shape.yml`。增加 3D 模型时，优先在
同一 `models/` 目录放置一个 Xacro 入口及其 `meshes/` 依赖，并在原装饰器的 `model` 中增加
`format: xacro`、`entry` 和 `macro`。同一 Xacro 默认同时作为 Web、kinematics 和 collision
来源；只有实际存在不同优化产物时才增加用途覆盖。

## 安装、检查和构建

在可运行 Uni-Lab-OS 的 Python 3.11 环境中：

```bash
python -m pip install -e . --no-deps
./scripts/check-package.sh
./scripts/build-package.sh
python -m pytest
```

wheel 输出到 `dist/`。`check-package.sh` 先编译完整 Catalog，再用 `--workspace` 做 OS
只读检查；`build-package.sh` 通过 package manager 构建并审计 clean wheel。设备、资源、工作流和
模型均由 Catalog 发现，Graph 是设备实例、物料拓扑、连接参数和本次激活选择的唯一权威来源。
仓库不再包含运行时 Profile。

Workflow 新代码遵循 Core 的
[`Workflow Python 写法规范`](https://github.com/Uni-Lab-OS/Uni-Lab-Core/blob/main/docs/guides/python-workflow-authoring-standard.md)。当前包含 13 个
Workflow；`s06_material.py` 是 Action 级 `ResourceSlot` 线性链参考实现。

## 本地联调

启动带 FE authoring API 的单进程测试 OS：

```bash
./scripts/start-authoring-os.sh
```

启动真实 runtime OS，或启动固定为测试模式的 OS：

```bash
./scripts/start-runtime-os.sh
./scripts/start-test-os.sh
```

OPC UA 仿真与 Edge 联调可直接使用 5 节点演示工作流
`szlab_poly_studio/workflows/robot_liquid_stirring_demo.py`；对应握手器启动命令见
[`docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md`](docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md)。

机械臂 MoveIt S1 仿真使用独立执行 profile，默认不启动 RViz、也不连接 PLC：

```bash
./scripts/start-moveit-sim-os.sh
# 仅需要可视化时：
UNILAB_VISUAL=rviz ./scripts/start-moveit-sim-os.sh
```

MoveIt 核心由独立 `szlab-moveit-sim.json` 中的
`standard_execution_backend=moveit_sim` 启动，和 `--visual` 正交。UI/Workflow
只能调用 `simulate_site_motion`；生产 `pick/place` 会 fail-closed，因为当前模型尚无
真实夹爪动作与生产 Inventory 见证。该仿真 Action 只接受 `target_site`、
`payload_profile` 和仿真 fixture 标识，不接受生产 ResourceSlot。示例关节序列仅用于
仿真联调，不能作为生产批准点位。

该独立 MoveIt graph 不包含 PLC 节点，也不会改写任何网络配置。真机接入前必须单独核验 IP、NodeId、
账号、联锁、急停、物料占用和恢复语义。

SZLab 前端 E2E 截图见 [`docs/E2E_SCREENSHOTS.md`](docs/E2E_SCREENSHOTS.md)，迁移前 12 个历史
工作流的代码与 DAG 截图见
[`docs/ALL_WORKFLOW_SCREENSHOTS.md`](docs/ALL_WORKFLOW_SCREENSHOTS.md)。远端 OPC UA 仿真、
FE-OS 启动和排障命令见
[`docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md`](docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md)。全部工作流的
真机仿真结果见
[`docs/ALL_WORKFLOWS_LIVE_E2E_20260730.md`](docs/ALL_WORKFLOWS_LIVE_E2E_20260730.md)，动作与 PLC
日志规范见 [`docs/SZLAB_ACTION_LOGGING.md`](docs/SZLAB_ACTION_LOGGING.md)。

## 来源与许可

来源映射见 [`migration/manifest.yaml`](migration/manifest.yaml)，完整来源见 [`NOTICE`](NOTICE)。
上游设备驱动标记为 DP Technology Proprietary License；除非权利人明确授权，本仓库应保持
私有。详见 [`LICENSE`](LICENSE)。
