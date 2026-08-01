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
│   ├── profiles/default/
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

wheel 输出到 `dist/`。`check-package.sh` 暂时通过现有 OS 的兼容入口
`--devices ./szlab_poly_studio` 做 AST 检查；包内 2.5D 清单采用 `shape.yml`，避免现有 OS 把
`devices/**/shape.yaml` 误判成旧式 YAML 注册表。模型入口由装饰器显式指定，扩展名不参与发现。
Issue #147 里的 OS package manager 和
`--workspace .` 尚未落地前，不能把“目录已经是 workspace”误写成“当前 OS 已支持 workspace
启动”。

## 本地联调

启动离线 authoring bridge：

```bash
./scripts/start-authoring-bridge.sh
```

启动 runtime bridge 与测试 Edge：

```bash
./scripts/start-runtime-bridge.sh
./scripts/start-test-os.sh
```

OPC UA 仿真与 Edge 联调可直接使用 5 节点演示工作流
`szlab_poly_studio/workflows/robot_liquid_stirring_demo.py`；对应握手器启动命令见
[`docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md`](docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md)。

默认图中的直连 PLC 驱动均为 `auto_connect: false`。真机接入前必须单独核验 IP、NodeId、
账号、联锁、急停、物料占用和恢复语义。

SZLab 前端 E2E 截图见 [`docs/E2E_SCREENSHOTS.md`](docs/E2E_SCREENSHOTS.md)，12 个生产工作流
的代码与 DAG 截图见
[`docs/ALL_WORKFLOW_SCREENSHOTS.md`](docs/ALL_WORKFLOW_SCREENSHOTS.md)。远端 OPC UA 仿真、
Bridge/Edge 启动和排障命令见
[`docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md`](docs/SZLAB_OPCUA_SIM_STARTUP_DEBUG.md)。全部工作流的
真机仿真结果见
[`docs/ALL_WORKFLOWS_LIVE_E2E_20260730.md`](docs/ALL_WORKFLOWS_LIVE_E2E_20260730.md)，动作与 PLC
日志规范见 [`docs/SZLAB_ACTION_LOGGING.md`](docs/SZLAB_ACTION_LOGGING.md)。

## 来源与许可

来源映射见 [`migration/manifest.yaml`](migration/manifest.yaml)，完整来源见 [`NOTICE`](NOTICE)。
上游设备驱动标记为 DP Technology Proprietary License；除非权利人明确授权，本仓库应保持
私有。详见 [`LICENSE`](LICENSE)。
