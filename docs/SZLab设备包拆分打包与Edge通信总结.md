# SZLab 设备包拆分、打包与 Edge 通信总结

> 整理日期：2026-07-29  
> 分析对象：`Uni-Lab-SZLab`  
> 内容范围：设备拆分与打包、设备包目录和信息、设备包与 Uni-Lab Edge 的通信方式

## 1. 核心结论

`Uni-Lab-SZLab` 已经完成了将 SZLab 和 AI4C 设备实现从 Uni-Lab-OS 主仓库拆分为外部 Python 包的主要工作。

当前仓库不是“一台物理设备对应一个 wheel”，而是一个 monorepo，产出两个可分别安装、测试和发布的 Python distribution：

| 设备包 | Python distribution | 内容 |
| --- | --- | --- |
| SZLab 聚合物工作站 | `unilabos-szlab-poly-studio` | PLC、S1、S04～S09、机械臂、物料、warehouse、deck 和工作流 |
| AI4C 工作站 | `unilabos-ai4c-robot` | AI4C PLC、机械臂和调试工作流 |

需要特别注意：

1. 设备包不是通过 MQTT、gRPC 等协议作为独立服务连接 Edge。
2. 设备包安装在 Edge 的 Python 环境中，由 Uni-Lab-OS 扫描、加载和实例化。
3. `pip install` 目前只完成代码安装，并不代表 Edge 会自动启用该设备包。
4. 运行时仍需显式指定 `--devices`、`--profile` 和 `--graph`。
5. 当前 wheel 内的 Profile 副本不能完整发现装饰器设备动作，尚需完善“安装后发现”机制。

相关入口：

- [仓库说明](../README.md)
- [SZLab Profile](../packages/szlab_poly_studio/package.yaml)
- [AI4C Profile](../packages/ai4c_robot/package.yaml)
- [SZLab device spec](../specs/szlab_poly_studio.yaml)
- [AI4C device spec](../specs/ai4c_robot.yaml)

---

## 2. 如何把一般设备从 Uni-Lab 中分离并打成设备包

### 2.1 确定设备包边界

设备包的边界不应简单按照 Python 文件或物理设备数量划分，更适合根据部署和维护边界判断：

- 是否部署在同一台 Edge。
- 是否需要一起安装、升级和回滚。
- 是否共用一套 PLC、SDK、网络连接或配置。
- 是否由同一团队维护。
- 是否存在大量包内调用。
- 是否能够独立测试和发布。

SZLab 采用的划分方式是：

- 聚合物工作站中的 PLC、S1、S04～S09、机械臂、物料和 warehouse 作为一个包。
- AI4C PLC 和 AI4C 机械臂作为另一个包。

因此，“设备包”更准确地表示一组具有共同部署生命周期的设备能力，不必严格等同于一台物理设备。

### 2.2 固定上游版本和迁移来源

拆包前应记录：

- 原始仓库、分支和 commit。
- 被提取的源代码目录。
- 旧工作流和 UI preset。
- CSV、JSON 等设备数据来源。
- 导入路径的变化。
- 动作名和合同的变化。

SZLab 将这些信息记录在 [migration/manifest.yaml](../migration/manifest.yaml) 中。当前迁移基线为：

```text
源设备代码：styxhuang/Uni-Lab-OS dev@d58a8c0...
模板和 schema：Uni-Lab-Templates main@5e44020...
```

`migration/legacy/` 保存旧 preset、运行配置、工作流和 PLC CSV，仅用于审计，不作为当前生产配置源。

### 2.3 提取完整依赖闭包

不能只复制设备主类，还需要一起提取设备运行所依赖的内容：

- 硬件通信客户端。
- 设备动作实现。
- PLC、传感器和工位状态逻辑。
- CSV NodeId 表。
- JSON 工艺参数。
- 资源、容器、deck、warehouse。
- 工作流。
- 包内 helper 和必要的基类。
- 对应测试。

例如，AI4C 原来依赖 Uni-Lab-OS 内部的 OPC UA 基类。拆包后，AI4C 在自己的包中提供了：

```text
packages/ai4c_robot/ai4c_robot/opcua.py
```

这样可以避免继续依赖：

```python
unilabos.devices.workstation.AI4C.base_opcua_client
```

拆包后的代码可以继续依赖 Uni-Lab-OS 的公开 API，例如：

```python
unilabos.registry.decorators
unilabos.resources
unilabos.ros
unilabos.device_comms
```

但不应继续依赖 `unilabos.devices.*` 下其他内置设备的具体实现。

### 2.4 改写 Python namespace

原来位于 Uni-Lab-OS 内部的导入：

```python
from unilabos.devices.workstation.szlab_poly_studio.plc import ...
```

拆包后应改为包自己的 namespace：

```python
from szlab_poly_studio.plc import ...
```

同时还需要处理：

- CSV 和 JSON 路径改为相对于安装后的 Python 包解析。
- 删除开发者本机绝对路径。
- 删除主仓库私有模块引用。
- 保证 SZLab 和 AI4C 两个 distribution 不互相 import。

当前仓库通过 `tests/test_repository_hygiene.py` 检查两个 distribution 的交叉导入。

### 2.5 使用装饰器注册设备、动作、状态和资源

设备类通过 Uni-Lab-OS 的装饰器注册：

```python
from unilabos.registry.decorators import (
    action,
    device,
    not_action,
    topic_config,
)


@device(
    id="my_device",
    display_name="我的设备",
    category=["custom"],
    description="设备说明",
)
class MyDevice:
    @action(description="执行设备动作")
    def run(self, speed: int) -> dict:
        return {"success": True}

    @property
    @topic_config()
    def status(self) -> str:
        return "Idle"

    @not_action
    def internal_helper(self) -> None:
        pass
```

主要规则：

- 每个设备类使用 `@device`。
- 可被工作流、调度器或前端调用的方法使用 `@action`。
- 不应暴露为动作的公共 helper 使用 `@not_action`，或者改成私有方法。
- 状态属性使用 `@property` 和 `@topic_config()`。
- 动作名应为稳定的 Python identifier。
- 不再使用历史 `auto-<method>` 动作名。
- 物料、容器、deck 和 warehouse 使用 `@resource`。

SZLab 当前注册：

- 9 个 SZLab 设备。
- 2 个 AI4C 设备。
- 15 个 SZLab 资源。

### 2.6 建立 device-template v2 合同

device-template v2 描述逻辑设备及其动作合同，主要包括：

- 设备 ID、显示名称和分类。
- 动作 ID 和说明。
- 输入参数、类型和数值范围。
- 动作返回值。
- 物料输入和输出。
- 物料身份是否保持。
- 动作需要独占或共享的资源。
- 预计执行时间和超时。
- retry、cancel、disconnect、estop 等恢复语义。

例如，SZLab 的 `run_stirring` 包括：

```yaml
id: run_stirring
execution_kind: device_macro
params:
  - name: position
    type: integer
    required: true
    minimum: 1
    maximum: 6
  - name: speed
    type: number
    required: true
material:
  mode: pass_through
resource_claims:
  - resource_ref: s04
    resource_type: stirrer_station
    mode: exclusive
timing:
  estimated_duration_s: 60
  timeout_s: 600
```

完整合同位于：

```text
specs/szlab_poly_studio.yaml
specs/ai4c_robot.yaml
```

### 2.7 建立 Profile v1

Profile 将逻辑设备合同绑定到运行时驱动、资源拓扑和动作宏。

主要字段包括：

```yaml
schema_version: 1
profile_id: my_device_package
device_spec: ../../specs/my_device_package.yaml

default_device_binding:
  device_id: my_device
  driver_key: generic_plc_macro
  connection_ref: MY_DEVICE_CONNECTION

resource_topology:
  resources: []

driver_config:
  macros: {}

workflow_importers:
  - schema: unilab.python/v1
    kind: workflow
    codec: python_ast_v1
```

Profile 负责：

- 选择逻辑驱动。
- 定义连接引用。
- 定义资源拓扑。
- 将逻辑动作映射到驱动调用。
- 声明工作流导入方式。

需要区分：

- Profile 中的动作是逻辑动作合同。
- `@device/@action` 扫描得到的是实际物理设备动作。
- `--devices` 激活实际设备类型。
- `--profile` 激活逻辑 Profile。
- `--graph` 决定创建哪些实际设备实例。

### 2.8 建立部署图

部署图描述 Edge 上实际存在的设备和资源实例，例如：

```json
{
  "id": "szlab_mixer_stirrer",
  "name": "S04 磁搅",
  "type": "device",
  "class": "szlab_mixer_stirrer",
  "config": {
    "url": "opc.tcp://127.0.0.1:50100/",
    "csv_path": "magnetic_stirring/magnetic_stirring_nodes.csv",
    "auto_connect": false
  }
}
```

当前部署图位于：

```text
deployment/graphs/local-debug.json
deployment/graphs/szlab-local-debug.json
deployment/graphs/ai4c-local-debug.json
```

建议至少区分三类配置：

1. 示例配置：不含密码，默认不连接硬件。
2. 测试配置：只连接 localhost 模拟器。
3. 现场部署覆盖：包含真实 IP、NodeId、证书和账号，保存在受控配置系统中，不提交到 Git。

### 2.9 配置 Python distribution

每个可发布设备包需要独立的 `pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "unilabos-my-device"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "opcua>=0.98.13",
]

[project.optional-dependencies]
runtime = ["unilabos>=0.11.3"]

[tool.setuptools.packages.find]
include = ["my_device*"]

[tool.setuptools.package-data]
my_device = [
  "*.csv",
  "*.json",
  "profile/*.yaml",
  "workflows/*.py",
]
```

package data 必须显式包含：

- CSV。
- JSON。
- YAML。
- 工作流源码。
- 设备 spec 和 Profile。
- 设备运行所需的其他非 Python 文件。

构建完成后应使用以下命令检查 wheel 的真实内容：

```bash
unzip -l dist/my_device/*.whl
```

### 2.10 校验和构建

SZLab 当前提供：

```bash
./scripts/check-szlab-package.sh
./scripts/check-ai4c-package.sh

./scripts/build-szlab-package.sh
./scripts/build-ai4c-package.sh
```

外部包 Registry 检查的核心命令为：

```bash
unilab \
  --check_mode \
  --devices ./my_device \
  --external_devices_only
```

完整验证至少应覆盖：

- Python import。
- `@device/@resource/@action` Registry 扫描。
- Profile v1 schema。
- device-template v2 schema。
- Profile 可加载性。
- 动作宏和参数一致性。
- 资源尺寸、容量和单位。
- 部署图引用的 class 是否存在。
- 默认配置是否禁止误连真机。
- 工作流 AST 编译。
- wheel 内容。
- 从安装后的 wheel 启动，而不只从源码目录启动。

### 2.11 当前安装后发现机制的缺口

当前两个 wheel 都包含：

```text
<python_package>/profile/package.yaml
<python_package>/profile/device.yaml
```

但是 ProfileLoader 查找装饰器设备包时使用：

```python
decorated_root = profile_path.parent / profile_id
```

源码根部 Profile 的布局是：

```text
packages/szlab_poly_studio/
├── package.yaml
└── szlab_poly_studio/
```

所以可以找到同级 Python 包。

wheel 内的布局是：

```text
szlab_poly_studio/
└── profile/
    ├── package.yaml
    └── device.yaml
```

此时加载器会寻找：

```text
szlab_poly_studio/profile/szlab_poly_studio/
```

该目录不存在，因此装饰器物理动作不会被合并到 Profile 动作目录。

实际加载结果：

| Profile 入口 | 总动作数 | 装饰器动作数 |
| --- | ---: | ---: |
| SZLab 源码根部 `package.yaml` | 78 | 71 |
| SZLab wheel 内 Profile 副本 | 7 | 0 |
| AI4C 源码根部 `package.yaml` | 19 | 11 |
| AI4C wheel 内 Profile 副本 | 8 | 0 |

因此当前 wheel 是“包含了 Profile 文件”，但还没有完全达到“安装后独立加载完整 Profile”的目标。

建议后续：

- 让 ProfileLoader 使用 `importlib.util.find_spec(profile_id)` 定位已安装 Python 包；或者
- 建立正式的 Profile entry point，显式声明 Profile 和设备源码入口；并且
- 增加“安装 wheel 后加载 Profile”的集成测试。

---

## 3. 设备包目录结构及其包含的信息

### 3.1 仓库级结构

```text
Uni-Lab-SZLab/
├── packages/
│   ├── szlab_poly_studio/
│   └── ai4c_robot/
├── specs/
├── schemas/
├── deployment/
│   └── graphs/
├── migration/
├── scripts/
├── tests/
├── docs/
├── dist/
└── runtime/
```

各目录职责：

| 目录 | 作用 | 是否进入 wheel |
| --- | --- | --- |
| `packages/` | 两个独立 Python distribution | 部分进入 |
| `specs/` | device-template v2 权威源码 | 通过包内副本进入 |
| `schemas/` | Profile/device spec 的 JSON Schema | 不进入 |
| `deployment/` | Edge 实例部署图和本地配置 | 不进入 |
| `migration/` | 旧代码和配置迁移证据 | 不进入 |
| `scripts/` | 检查、构建、启动脚本 | 不进入 |
| `tests/` | schema、Registry、资源和工作流测试 | 不进入 |
| `dist/` | 构建后的 wheel | 构建产物 |
| `runtime/` | 本地 journal 和运行数据 | 不应进入 |

### 3.2 SZLab distribution 结构

```text
packages/szlab_poly_studio/
├── README.md
├── pyproject.toml
├── package.yaml
└── szlab_poly_studio/
    ├── __init__.py
    ├── plc.py
    ├── materials.py
    ├── warehouses.py
    ├── decks.py
    ├── stack_status.py
    ├── szlab_plc_0702.csv
    ├── magnetic_stirring/
    ├── photoshotting/
    ├── pump/
    ├── robot/
    ├── s1/
    ├── s07_solid_addition/
    ├── decap_s08/
    ├── s09_pipetting_station/
    ├── workflows/
    └── profile/
        ├── package.yaml
        └── device.yaml
```

### 3.3 AI4C distribution 结构

```text
packages/ai4c_robot/
├── README.md
├── pyproject.toml
├── package.yaml
└── ai4c_robot/
    ├── __init__.py
    ├── opcua.py
    ├── plc.py
    ├── robot.py
    ├── ai4c_nodes.csv
    ├── workflows/
    └── profile/
        ├── package.yaml
        └── device.yaml
```

### 3.4 包中包含的信息

#### 设备实现

- 初始化参数。
- 硬件连接参数。
- 动作实现。
- 状态属性。
- timeout 和错误处理。
- 跨设备调用。
- 设备启动和关闭逻辑。

#### 通信信息

- OPC UA URL。
- 用户名和密码参数。
- NodeId 映射。
- CSV 节点表。
- polling/subscription 配置。
- heartbeat。
- 工艺握手变量。

密码、token、证书私钥和现场敏感地址不应直接写入包。

#### 资源信息

- 物料类型。
- 物料尺寸，统一使用 mm。
- 物料容量，统一使用 μL。
- warehouse 容量。
- site 和槽位。
- deck 中的相对位置。
- 物料输入、输出和身份关系。

#### 动作合同

- 动作 ID。
- 输入和输出 schema。
- 参数范围。
- 物料 effect。
- 资源独占/共享规则。
- 预计耗时。
- timeout。
- cancel、disconnect、estop 和 retry 语义。

#### 工作流

- 当前生产工作流位于 `workflows/*.py`。
- 使用受限 Python AST 编译器解析。
- 编译为 Canonical v2。
- 不使用 `eval`、`exec` 或 import 用户工作流来构建 DAG。

#### 打包元数据

- distribution 名。
- 版本。
- Python 版本要求。
- 依赖。
- 可选依赖。
- package data。
- 构建 backend。

---

## 4. 设备包如何与 Uni-Lab Edge 通信

### 4.1 总体通信图

```text
Uni-Lab 桌面/Web 前端
    │
    │ HTTP + WebSocket
    │ 127.0.0.1:8014
    ▼
local_bridge
    │
    │ schedule WebSocket
    │ 127.0.0.1:8890/api/v1/ws/schedule
    │
    │ 下行：task_dag、cancel、debug、reconcile
    │ 上行：job_status、事件、物料快照
    ▼
Uni-Lab-OS / Edge Scheduler
    │
    │ ROS2 Action / Topic
    │ 或 simple backend 直接 Python 调用
    ▼
设备包驱动实例
    │
    │ OPC UA / TCP / 厂商 SDK
    ▼
PLC / 仪器 / 机械臂 / 传感器
```

设备包和 Edge 之间不是典型的远程服务关系，而是插件与宿主运行时的关系。

### 4.2 设备包如何进入 Edge

Edge 启动时需要：

1. 安装或挂载设备包代码。
2. 使用 `--devices` 指定要扫描的 Python 包目录。
3. 使用 `--profile` 加载 Profile。
4. 使用 `--graph` 选择实际设备实例。
5. Registry 扫描设备包中的装饰器。
6. 根据 graph 中的 `class` 动态 import 驱动类。
7. 实例化设备，并包装为 ROS2 device node。

当前启动示例：

```bash
unilab \
  --graph deployment/graphs/local-debug.json \
  --config deployment/local_config.py \
  --devices packages/szlab_poly_studio/szlab_poly_studio \
  --devices packages/ai4c_robot/ai4c_robot \
  --profile packages/szlab_poly_studio/package.yaml \
  --profile packages/ai4c_robot/package.yaml \
  --external_devices_only \
  --backend ros
```

### 4.3 Registry 扫描

Uni-Lab-OS 使用 AST 静态扫描提取：

- `@device`
- `@resource`
- `@action`
- 状态和参数 schema
- 类的 module 路径

静态扫描阶段不需要先 import 全部设备模块，可以减少不必要的 SDK 加载和启动副作用。

当 graph 中引用：

```json
{
  "class": "szlab_mixer_stirrer"
}
```

Edge 会在 Registry 中找到该 class 对应的 Python 实现，然后动态 import。

### 4.4 ROS2 运行时

物理设备类会被包装为 `ROS2DeviceNode`。

每个设备实例的 namespace 为：

```text
/devices/<device_id>
```

例如：

```text
/devices/AI4C_plc
/devices/AI4C_robot_arm
/devices/szlab_mixer_stirrer
```

Edge 会为设备创建：

- 状态 publisher。
- 状态 subscriber。
- ROS ActionServer。
- 跨设备 ActionClient。
- 资源管理 service client。

动作通常位于：

```text
/devices/<device_id>/<action_name>
```

通用 Python 驱动命令可通过：

```text
/devices/<device_id>/_execute_driver_command
```

设备状态通常通过：

```text
/devices/<device_id>/<status_name>
```

发布。

### 4.5 跨设备通信

AI4C 展示了典型的“PLC 设备 + 业务设备”结构：

```text
AI4C_robot_arm
    │
    ├── 订阅 AI4C_plc 状态 Topic
    │
    └── 调用 AI4C_plc driver command Action
             │
             ▼
          OPC UA PLC
```

`AI4C_robot_arm` 会：

- 订阅 `/devices/AI4C_plc/robotic_arm_idle`。
- 订阅 `/devices/AI4C_plc/robotic_arm_action_complete`。
- 订阅各工位占用状态。
- 通过 `/devices/AI4C_plc/_execute_driver_command` 强制读取或写入 PLC。

这样可以避免多个业务设备分别创建重复 OPC UA 连接。

SZLab 中也存在类似结构：

- 公共 `szlab_poly_plc` 负责 PLC 连接。
- 部分工位可以通过 PLC gateway 共享读写。
- 部分独立工位仍使用自己的 OPC UA 客户端。

### 4.6 设备驱动与真实硬件通信

SZLab/AI4C 主要使用 OPC UA：

```text
Python 驱动
    │
    │ opc.tcp://<plc-host>:<port>/
    ▼
OPC UA Server / PLC
```

通信内容包括：

- 连接和认证。
- 根据 CSV 或显式映射定位 NodeId。
- 读取设备状态。
- 写入工艺参数。
- OPC UA subscription。
- heartbeat。
- ready/allow-process/params-written/complete/reset 握手。
- timeout、disconnect 和错误处理。

当前本地部署图使用：

```yaml
auto_connect: false
```

防止调试环境误连真机。

真机配置必须单独验证：

- PLC 地址和端口。
- NodeId。
- 用户名、密码和证书。
- PLC 时钟。
- 变量类型和访问级别。
- 联锁和急停。
- 断线恢复和 reconcile。

详细清单见 [HARDWARE_BRINGUP.md](HARDWARE_BRINGUP.md)。

### 4.7 前端和 Edge 的通信

前端不直接连接设备包，也不应直接连接 Edge 内部 schedule WS。

前端只连接 local bridge：

```text
http://127.0.0.1:8014
```

主要接口包括：

```text
GET|PUT /api/v1/workflows/{id}/graph
POST    /api/v1/workflows:validate
POST    /api/v1/authoring/compile
POST    /api/v1/authoring/generate-python
POST    /api/v1/authoring/validate
POST    /api/v1/runtime/runs
GET     /api/v1/runtime/runs/{run_id}
GET     /api/v1/runtime/runs/{run_id}/nodes
GET     /api/v1/runtime/runs/{run_id}/events
POST    /api/v1/runtime/runs/{run_id}/commands
POST    /api/v1/runtime/runs/{run_id}/cancel
WS      /api/v1/runtime/events
GET     /api/v1/materials
GET     /api/v1/material-models
```

Bridge 与 OS 之间使用：

```text
ws://127.0.0.1:8890/api/v1/ws/schedule
```

消息方向：

```text
Bridge -> OS:
  task_dag
  cancel_task
  debug command
  reconcile request

OS -> Bridge:
  job_status
  debug event
  material snapshot
  host ready
```

端口职责：

| 端口 | 使用者 | 用途 |
| --- | --- | --- |
| `8014` | 前端/桌面端 | HTTP、运行事件 WS、物料和模型接口 |
| `8890` | local bridge 与 OS | Edge 内部 schedule WebSocket |
| `8002` 或部署端口 | Edge 内部 HTTP | OS 内部 Registry、模板等接口 |
| `4840` 或现场端口 | 设备驱动与 PLC | OPC UA |

### 4.8 网络安全要求

- local bridge 默认只监听 `127.0.0.1`。
- schedule WS 只用于 Edge 内部通信。
- 不应直接把 8014、8890 或 PLC 端口暴露到实验室公网。
- 前端和 Edge 不在同一台机器时，应使用 SSH 隧道或经过认证的受控代理。
- 设备包中不得提交密码、token、私钥和可公网访问的 PLC 地址。

远程访问示例：

```bash
ssh -N -L 8014:127.0.0.1:8014 edge-user@edge-host
```

前端仍连接：

```text
http://127.0.0.1:8014
```

---

## 5. 推荐的标准设备包骨架

综合 SZLab 当前实践和需要补齐的部分，一个一般设备包可以采用：

```text
my_device_package/
├── README.md
├── LICENSE
├── NOTICE
├── CHANGELOG.md
├── pyproject.toml
├── package.yaml
├── my_device_package/
│   ├── __init__.py
│   ├── device.py
│   ├── comms/
│   │   ├── __init__.py
│   │   └── opcua.py
│   ├── resources.py
│   ├── data/
│   │   ├── nodes.csv
│   │   └── parameters.json
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── example_workflow.py
│   └── profile/
│       ├── package.yaml
│       └── device.yaml
├── deployment/
│   ├── local-debug.json
│   └── config.example.py
├── scripts/
│   ├── check-package.sh
│   └── build-package.sh
└── tests/
    ├── test_registry.py
    ├── test_profile.py
    ├── test_resources.py
    ├── test_workflows.py
    └── test_installed_wheel.py
```

其中必须明确：

- 哪些内容属于 Python wheel。
- 哪些属于部署配置。
- 哪些是现场敏感配置。
- 哪些是迁移证据。
- 哪些是测试和文档。

---

## 6. 建议后续优先级

1. 修复 wheel 内 Profile 无法发现装饰器动作的问题。
2. 建立正式的已安装 Profile/设备包发现机制。
3. 增加从 wheel 安装后启动的集成测试。
4. 将部署图作为独立、版本化的部署产物管理。
5. 明确设备包版本和 Uni-Lab-OS 兼容范围。
6. 将凭据、现场 IP 和 NodeId 覆盖移到受控部署配置。
7. 持续验证 cancel、disconnect、timeout、急停和重启后的 reconcile 语义。

完成这些工作后，设备包才能真正达到：

```text
独立开发
→ 独立测试
→ 独立构建
→ 独立安装
→ Edge 自动发现
→ 受控激活
→ 独立升级和回滚
```
