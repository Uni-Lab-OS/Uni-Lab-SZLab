# SZLab FE-OS Workspace 启动与 OPC UA 仿真排障

本文档适用于完成 WorkflowTask/FE-OS migration 的 Uni-Lab-OS。领域仓库以
`--workspace` 显式挂载；一个 OS 进程同时提供设备运行、Workflow Authoring API 和 Web API。

## 1. 权威边界

- `pyproject.toml` 定义 distribution、import package 与运行依赖。
- `package.yaml` 只登记稳定 Workflow UUID 与源码位置。
- PackageCatalog 通过 AST 发现设备、资源、Workflow 和模型资产，不执行领域模块。
- Graph 是设备/物料实例、拓扑、连接参数和本次激活选择的唯一权威来源。
- `runtime/`、`unilabos_data/` 与 Workflow 数据库都是本地运行产物，不进入 wheel。

启动链路如下：

```text
Uni-Lab-SZLab workspace
  ├─ pyproject.toml + package.yaml + decorators ──> PackageCatalog
  └─ deployment/graphs/*.json ───────────────────> selected instances/config
                                                        │
                                                        v
                                              one Uni-Lab-OS process
                                              ├─ FE authoring API
                                              ├─ runtime API
                                              └─ device/resource runtime
```

## 2. 环境

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

export UNILAB_OS_ROOT=/home/changjunhan/Uni-Lab-Core/.worktrees/uni-lab-os-f006-package-catalog
export UNILAB_PYTHON=/home/changjunhan/.micromamba/envs/unilab/bin/python
export PYTHONPATH="${UNILAB_OS_ROOT}:$(pwd)${PYTHONPATH:+:${PYTHONPATH}}"
```

合并后可将 `UNILAB_OS_ROOT` 改回正式的 `Uni-Lab-OS` checkout。

先验证 workspace：

```bash
"${UNILAB_PYTHON}" -m unilabos.app.main package inspect --path "$(pwd)"
"${UNILAB_PYTHON}" -m pytest
```

预期 Catalog 包含 9 个设备、14 个资源、12 个 Workflow 和 12 个模型资产。

## 3. 单设备调试

从完整 Graph 复制一个待调试设备节点及其必要物料节点到新的 JSON。Catalog 仍会发现整个领域包，
但只有 Graph 中选中的实例会被创建；连接参数继续写在节点的 `config` 中。

例如只调试 PLC 时，应至少保留：

```json
{
  "id": "szlab_poly_plc",
  "type": "device",
  "class": "community.szlab_poly_studio.szlab_poly_plc",
  "config": {
    "url": "opc.tcp://127.0.0.1:50100/",
    "csv_path": "szlab_plc_0730.csv",
    "auto_connect": false
  }
}
```

启动命令：

```bash
"${UNILAB_PYTHON}" -m unilabos.app.main \
  --workspace "$(pwd)" \
  --graph /absolute/path/to/single-device.json \
  --config "$(pwd)/deployment/local_config.py" \
  --working_dir "$(pwd)/runtime/single-device" \
  --backend ros \
  --app_bridges fastapi \
  --port 18003 \
  --disable_browser \
  --skip_env_check
```

首次接真机前先保持 `auto_connect: false`，核验 URL、NodeId、账号、联锁、急停和恢复语义后再启用。

## 4. 全工作区离线调试

`start-authoring-os.sh` 使用完整本地图、`simple` backend 和 `--test_mode`，适合调试 FE、
Workflow 编译、Graph 与物料展示：

```bash
UNILAB_OS_ROOT="${UNILAB_OS_ROOT}" \
UNILAB_PYTHON="${UNILAB_PYTHON}" \
  ./scripts/start-authoring-os.sh
```

默认 API 地址为 `http://127.0.0.1:8014`。前端可通过自己的本地 OS 地址参数连接该端口。

## 5. OPC UA 仿真与完整 Runtime

先启动 OPC UA server/握手器，再启动 OS：

```bash
UNILAB_OS_ROOT="${UNILAB_OS_ROOT}" \
UNILAB_PYTHON="${UNILAB_PYTHON}" \
UNILAB_SZLAB_GRAPH="$(pwd)/deployment/graphs/szlab-ideawit-sim.json" \
  ./scripts/start-runtime-os.sh
```

只验证运行链路、不下发真实硬件动作时增加：

```bash
UNILAB_TEST_MODE=1 ./scripts/start-runtime-os.sh
```

默认 OS API 地址为 `http://127.0.0.1:18003`。Workflow Authoring 与 Runtime 使用该进程内的
同一 TemplateCatalog 和 WorkflowStore，不需要额外的调度中转进程。

## 6. 后台启动

```bash
mkdir -p runtime/ideawit-e2e/logs

nohup env \
  UNILAB_OS_ROOT="${UNILAB_OS_ROOT}" \
  UNILAB_PYTHON="${UNILAB_PYTHON}" \
  UNILAB_SZLAB_GRAPH="$(pwd)/deployment/graphs/szlab-ideawit-sim.json" \
  ./scripts/start-runtime-os.sh \
  > runtime/ideawit-e2e/logs/os.log 2>&1 &

printf '%s\n' "$!" > runtime/ideawit-e2e/os.pid
tail -f runtime/ideawit-e2e/logs/os.log
```

停止：

```bash
kill -TERM "$(sed -n '1p' runtime/ideawit-e2e/os.pid)"
```

## 7. 常见问题

### Catalog 编译失败

运行 `package inspect`，按结构化 diagnostic 修复。常见原因是：

- distribution 名归一化后与 import package 不一致；
- `package.yaml` 的 UUID 或源码路径与 decorator 不一致；
- decorator 使用动态 ID 或动态模型路径；
- wheel 未包含 Catalog closure 中的源码/资产。

### Workflow 未被发现

确认 `package.yaml` 已登记对应 UUID，源码位于
`szlab_poly_studio/workflows/<name>.py`，且 `@workflow_definition.workflow_uuid`
完全相同。仅放置一个带 decorator 的 Python 文件不会自动成为持久 Workflow source。

### Workflow 编译提示 selector 无效

设备选择器必须是模块级、有绝对导入类型注解的赋值：

```python
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from unilabos.workflow.authoring import device

szlab_mixer_pump: SzlabMixerPumpDevice = device("szlab_mixer_pump")
```

Workflow 参数必须是 keyword-only；每个 action result 必须绑定到唯一名字，并使用稳定的
`# unilab:node_uuid=...` anchor。

### Graph class 不存在

Graph 中的 `class` 必须使用 Catalog FQID，例如
`community.szlab_poly_studio.szlab_mixer_pump`，不能使用旧的非命名空间 ID。

### 连接失败

优先检查 Graph 节点 `config`，再检查网络与 OPC UA server。不要把 URL、串口、账号或连接开关
移回 Python 默认值、Profile 或额外启动配置。
