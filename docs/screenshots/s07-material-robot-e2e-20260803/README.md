# S07 双物料流 / ROS E2E 证据（2026-08-03）

## 最终结果

- 工作流：`S07 粉桶与烧杯搬运后固体称量`
- Workflow UUID：`5e7ce142-bf5a-5d30-8666-fdf5374941f1`
- Applied revision：`2`
- Applied Graph：`12` 节点、`9` 条边
- Task UUID：`6d63e2ae-ea19-4279-8b8e-92a504f6b447`
- Task 状态：`succeeded`
- Job：`10/10` succeeded，全部 `error_info=[]`
- 运行时间：`2026-08-03T06:35:43.642965Z` 至 `2026-08-03T06:36:13.666009Z`
- OS Task 日志窗口：`33739`–`43343` 行，`ERROR/Traceback/Exception/FAILED/failed` 为 `0`
- `添加物料失败` / `login verification`：整份本轮 OS 日志中均为 `0`
- 浏览器控制台 error：`[]`

最终截图：

- [完整画布、MaterialSource palette 与 Task 10/10](./material-flow-clean-task-10-of-10.png)
- [放大后的成功物料流](./material-flow-clean-readable-task-10-of-10.png)
- [折中缩放成功物料流](./material-flow-clean-balanced-task-10-of-10.png)

`workflow-task-ros-e2e-final.png` 是修复前失败记录，保留用于对比，不是最终结果。

## 分支与工作树

- Uni-Lab-OS：`/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/os-material-integration`
  - 分支：`integration/workflow-task-runtime`
- SZLab package：`/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e`
  - 分支：`codex/szlab-material-robot-e2e`
- 前端：`/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/fe-os-migration-merge`
  - 分支：`integration/fe-os-migration`

## 确定性本地 E2E 边界

WorkflowTask 确实通过 ROS 后端执行；PLC/现场动作由本地确定性 OPC UA 服务器与
握手仿真器承接，没有连接真实设备。OS 未使用 `--test_mode`，并显式开启
`--enable_workflow_physical_execution`。这是完整 ROS/Action/调度/PLC 协议 E2E，
不是无硬件状态下对真实机械运动的声明。

完整启动 JSON：

- `runtime/material-robot-e2e-sim-full-v4/szlab-material-robot-e2e-full-v4.json`
- SHA-256：`e8fbb0a83172bca58030b79d755578208636cb6df4d36de280be9e9e3c9e4ee5`
- `129` nodes、`0` links
- PLC：`opc.tcp://127.0.0.1:50100/`、`auto_connect=true`、prefix `ns=4;s=上位机通讯|`
- 机械臂 standard actions、安全许可与远程自动许可均启用；journal 使用本轮独立路径

## 完整启动命令

本地 OPC UA：

```bash
PYTHONPATH=/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e \
/Users/dp/miniforge3/envs/unilab/bin/python -u \
  scripts/szlab_local_opcua_server.py \
  --endpoint 'opc.tcp://127.0.0.1:50100/'
```

S07 协议握手：

```bash
PYTHONPATH=/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e \
/Users/dp/miniforge3/envs/unilab/bin/python -u scripts/szlab_workflow_handshake.py serve \
  --workflow s07_material_dosing \
  --url 'opc.tcp://127.0.0.1:50100/' \
  --node-prefix 'ns=4;s=上位机通讯|' \
  --process-delay 0.5 \
  --poll-interval 0.1
```

从正确的 OS 分支使用 `unilab` CLI 启动 ROS OS：

```bash
PYTHONPATH=/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/os-material-integration:/Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e \
/Users/dp/miniforge3/envs/unilab/bin/unilab \
  --workspace /Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e \
  --graph /Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e/runtime/material-robot-e2e-sim-full-v4/szlab-material-robot-e2e-full-v4.json \
  --config /Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e/deployment/local_config.py \
  --working_dir /Users/dp/Design_projects/Uni-Lab-Core/.worktrees/szlab-material-robot-e2e/runtime/material-robot-e2e-sim-full-v4 \
  --backend ros \
  --app_bridges websocket fastapi \
  --edge_scheduler \
  --ros_domain_id 91 \
  --port 18003 \
  --disable_browser \
  --skip_env_check \
  --enable_workflow_physical_execution
```

前端：

```bash
pnpm --filter @unilab/kernel-web dev --host 127.0.0.1 --port 5173
```

浏览器：

```text
http://localhost:5173/?section=workflow&localOsUrl=http%3A%2F%2F127.0.0.1%3A18003&disable=postFx
```

OS 启动确认：

```text
14:33:24.201 edge scheduler ready (ordering=local-stable)
14:33:24.258 Backend ros started.
14:33:24.482 启动FastAPI服务器: 0.0.0.0:18003
```

## 双 MaterialSource 与 `resource_ref`

普通 Action 参数现在可把 `resource_ref('id')` 当作与 `device('id')` 相同风格的声明式
引用：编译后由 Inventory 解析为 `ResourceSlot`，不再要求作者手写 UUID。MaterialSource
的 `mount=resource_ref(...)` 继续保留；前端恢复原生特殊节点渲染，而不是普通 Action 节点。

| 节点 | 解析后的 mount UUID | 分配的 material UUID | 状态 |
|---|---|---|---|
| `source_beaker` | `29f43434-ff8b-5246-b924-a20cddd452fc` | `c6ab5682-b465-49fd-85cb-b20f360b71f4` | succeeded |
| `source_powder` | `fa7b0692-2e78-5d5e-b789-9b0dfffb5dc7` | `c1b69585-e278-479c-99b3-2e36e66d8a50` | succeeded |

两个 MaterialSource 在 `06:35:43.442056Z` 同时完成，两个并行分支均立即 ready。
前端分别显示 `物料来源 / 主样品 · 已有物料 / Material 输出端口` 和
`物料来源 / 试剂 · 已有物料 / Material 输出端口`；Action 节点显示对应 Material 轨道。

## 调度、机器人独占与最终汇合

| Action | started_at | finished_at |
|---|---|---|
| `picked_beaker` / robot | `06:35:43.653751Z` | `06:35:47.970936Z` |
| `placed_beaker` / robot | `06:35:48.023888Z` | `06:35:51.452185Z` |
| `committed_beaker` / Host | `06:35:51.547615Z` | `06:35:51.631148Z` |
| `picked_powder` / robot | `06:35:51.822685Z` | `06:35:55.057160Z` |
| `prepared_powder` / S07 | `06:35:55.186785Z` | `06:35:57.420491Z` |
| `placed_powder` / robot | `06:35:57.534071Z` | `06:36:01.241615Z` |
| `committed_powder` / Host | `06:36:01.495242Z` | `06:36:01.790053Z` |
| `dosed` / S07 | `06:36:01.861894Z` | `06:36:13.600401Z` |

四个 `szlab_mixer_robot` Action 没有重叠。两个分支并行 ready，但由同一设备资源锁
串行执行；最终 `dosed` 同时接收 `beaker` 和 `powder_cartridge`：

```json
{
  "success": true,
  "beaker_uuid": "c6ab5682-b465-49fd-85cb-b20f360b71f4",
  "powder_cartridge_uuid": "c1b69585-e278-479c-99b3-2e36e66d8a50",
  "commanded_mass_g": 1.0,
  "message": "S07 固体称量流程完成；PLC 未提供实测质量"
}
```

OPC 握手记录覆盖机器人 pick/place、S07 粉桶位准备和最终投粉，全部出现
`accepted -> completed -> reset`。

## 日志、浏览器和回归

本轮 OS 日志：

- `runtime/material-robot-e2e-sim-full-v4/logs/2026-08-03 14-33-22.log`
- `14:35:43.445 POST /api/v1/workflow-tasks 201`（由前端创建）
- `14:35:43.650 Workflow Task running`
- `14:36:13.601 最终 dose Job succeeded`
- `14:36:13.672 Workflow Task succeeded`
- Task 行窗口 `33739`–`43343` 的错误扫描为空

节点 palette 的一次启动期 `Failed to fetch` 在点击“重新读取”后恢复，MaterialSource
palette 与特殊节点均出现；最终浏览器 console 的 error 级日志为空。

回归结果：

```text
Uni-Lab-OS 定向回归：145 passed
SZLab package 定向回归：61 passed
workflow-editor：27 files / 159 tests passed
services：11 files / 105 tests passed
workflow-editor typecheck：passed
services typecheck：passed
local OPC UA server py_compile：passed
local OPC UA server Ruff：passed
```

OS 回归覆盖普通 Action `resource_ref(...)` 编译/Inventory 解析、ResourceSlot 同步/异步
ROS JSON 输入、单棵嵌套 ResourceTreeSet dump、Host 本地资源同步不隐式调用云客户端，
以及显式 material bridge 仍被保留。
