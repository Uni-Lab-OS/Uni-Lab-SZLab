# SZLab OPC UA 仿真启动与握手调试

本文档用于在本机启动最新版 `uni-lab-fe`、Uni-Lab local bridge、Uni-Lab Edge，
并使用独立 Python 握手仿真器测试 SZLab 工作流。

本文档对应的 OPC UA 仿真端为：

```text
opc.tcp://opcua.ideawit.com:4855/xuse_sim
```

NodeId 前缀为：

```text
ns=4;s=上位机通讯|
```

## 1. 通信边界

```text
最新版前端
  http://127.0.0.1:5173
          |
          | HTTP / WebSocket
          v
local bridge
  HTTP 127.0.0.1:8015
  schedule WS 127.0.0.1:8892
          |
          | task_dag / job_status
          v
Uni-Lab Edge
  HTTP 127.0.0.1:18003
          |
          | 所有业务设备只调用 szlab_poly_plc
          v
统一 PLC 通信模块 szlab_poly_plc
          |
          | OPC UA
          v
opcua.ideawit.com:4855/xuse_sim
          ^
          | 独立 PLC 侧握手响应
szlab_workflow_handshake.py
```

必须保持以下边界：

- `szlab_poly_plc` 是 Edge 内唯一持有 OPC UA 客户端连接的设备。
- 机械臂、S04、S05、S06、S07、S08、S09 只通过 `plc_device_id=szlab_poly_plc`
  调用统一 PLC 模块，不能各自创建 OPC UA 连接。
- `szlab_workflow_handshake.py` 是独立的 PLC 仿真端测试程序，不属于 Edge 业务设备，
  因此联调时服务器上通常会看到两个会话：Edge 的统一 PLC 会话和握手仿真器会话。
- 握手仿真器只访问 CSV 已创建的节点，不创建、补充或浏览生成新节点。

## 2. 固定路径与端口

| 项目 | 值 |
| --- | --- |
| SZLab 仓库 | `/home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab` |
| Uni-Lab-OS | `/home/changjunhan/Uni-Lab-Core/Uni-Lab-OS` |
| 最新前端 | `/home/changjunhan/Uni-Lab-Core/uni-lab-fe` |
| Python | `/home/changjunhan/.micromamba/envs/unilab/bin/python` |
| unilab CLI | `/home/changjunhan/.micromamba/envs/unilab/bin/unilab` |
| 仿真图 | `deployment/graphs/szlab-ideawit-sim.json` |
| PLC CSV | `szlab_poly_studio/devices/szlab_poly_plc/szlab_plc_0730.csv` |
| 前端端口 | `5173` |
| Bridge API | `8015` |
| Bridge schedule WS | `8892` |
| Edge API | `18003` |

端口可调整，但 Bridge 的 `--execution-http-url`、Edge 的 `--schedule_addr` 和前端的
`localOsUrl` 必须同步修改。

## 3. 启动前检查

### 3.1 Python 依赖

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python - <<'PY'
import opcua
import unilabos

print("opcua:", opcua.__file__)
print("unilabos:", unilabos.__file__)
PY
```

`unilabos` 应指向：

```text
/home/changjunhan/Uni-Lab-Core/Uni-Lab-OS/unilabos
```

### 3.2 CSV 和图配置

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

test -f szlab_poly_studio/devices/szlab_poly_plc/szlab_plc_0730.csv

jq '.nodes[] | select(.id == "szlab_poly_plc") | .config' \
  deployment/graphs/szlab-ideawit-sim.json
```

期望配置：

```json
{
  "url": "opc.tcp://opcua.ideawit.com:4855/xuse_sim",
  "csv_path": "szlab_plc_0730.csv",
  "auto_connect": true,
  "opcua_node_id_prefix": "ns=4;s=上位机通讯|"
}
```

`szlab_plc_0730.csv` 使用 UTF-16 制表符格式。不要用会自动改编码或分隔符的编辑器直接另存。
该 CSV 必须先导入仿真服务器，由仿真服务器创建变量。

检查图中只有主 PLC 配置 OPC UA：

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python -m pytest -q \
  tests/test_plc_csv_0730.py \
  tests/test_unified_plc_gateway.py
```

### 3.3 端口占用

```bash
ss -ltnp | rg ':(5173|8015|8892|18003)\b' || true
```

重复启动前，应先确认端口上的进程是否就是上一轮 SZLab 服务。不要直接终止不明进程。

## 4. 推荐启动方式：四个终端

交互式启动最适合调试，因为 Bridge、Edge 和握手器的日志可以分别观察。

### 4.1 终端一：启动真实 Bridge

真实模式 Bridge 不使用 `--offline`，也不向 Bridge 传物理图；物理图由 Edge 持有。

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

export PYTHONPATH="/home/changjunhan/Uni-Lab-Core/Uni-Lab-OS:/home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab${PYTHONPATH:+:${PYTHONPATH}}"

/home/changjunhan/.micromamba/envs/unilab/bin/python \
  deployment/local_bridge_entrypoint.py \
  --host 127.0.0.1 \
  --schedule-port 8892 \
  --api-port 8015 \
  --execution-http-url http://127.0.0.1:18003 \
  --journal-path runtime/ideawit-e2e/quick-debug.sqlite3 \
  --profile szlab_poly_studio/profiles/default/package.yaml
```

### 4.2 终端二：启动 Edge

Edge 必须使用 `szlab-ideawit-sim.json`，并且不要在 Edge 命令中重复传
`--profile`。Profile 由 Bridge 用于编译工作流；Edge 从物理图加载设备。

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

export PYTHONPATH="/home/changjunhan/Uni-Lab-Core/Uni-Lab-OS:/home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab${PYTHONPATH:+:${PYTHONPATH}}"

/home/changjunhan/.micromamba/envs/unilab/bin/unilab \
  --graph /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/deployment/graphs/szlab-ideawit-sim.json \
  --config /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/deployment/local_config.py \
  --working_dir /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/runtime/ideawit-e2e \
  --devices /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/szlab_poly_studio \
  --external_devices_only \
  --backend ros \
  --app_bridges websocket fastapi \
  --port 18003 \
  --schedule_addr ws://127.0.0.1:8892/api/v1/ws/schedule \
  --disable_browser \
  --skip_env_check
```

启动成功的关键日志：

```text
client connected!
Host node initialized.
Host node ready signal published
Uvicorn running on http://0.0.0.0:18003
```

`请求启动配置失败: 401` 是未登录云端时的提示；本地 Bridge/Edge 联调仍可继续。

### 4.3 终端三：启动最新版前端

```bash
cd /home/changjunhan/Uni-Lab-Core/uni-lab-fe

pnpm dev -- --host 127.0.0.1
```

访问：

```text
http://127.0.0.1:5173/?localOsUrl=http%3A%2F%2F127.0.0.1%3A8015
```

这里显式指定 `8015`，避免前端回退到默认的 `8014`。

### 4.4 终端四：启动独立握手仿真器

先打印所有工作流先决条件：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

/home/changjunhan/.micromamba/envs/unilab/bin/python \
  scripts/szlab_workflow_handshake.py list \
  --position 1 \
  --pump 1
```

只读检查远端值：

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python \
  scripts/szlab_workflow_handshake.py check \
  --url 'opc.tcp://opcua.ideawit.com:4855/xuse_sim' \
  --node-prefix 'ns=4;s=上位机通讯|' \
  --position 1 \
  --pump 1
```

启动握手：

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python -u \
  scripts/szlab_workflow_handshake.py serve \
  --url 'opc.tcp://opcua.ideawit.com:4855/xuse_sim' \
  --node-prefix 'ns=4;s=上位机通讯|' \
  --position 1 \
  --pump 1 \
  --process-delay 5.0 \
  --poll-interval 0.1
```

完整运行 `szlab_poly_studio/workflows/s06_robot.py`
时使用 S06 专用场景：

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python -u \
  scripts/szlab_workflow_handshake.py serve \
  --workflow s06_robot_workflow \
  --url 'opc.tcp://opcua.ideawit.com:4855/xuse_sim' \
  --node-prefix 'ns=4;s=上位机通讯|' \
  --pump 1 \
  --process-delay 5.0 \
  --poll-interval 0.1 \
  --max-actions 3
```

该场景从 `S06` 无烧杯开始，依次响应机器人任务号 11、S06 加液和机器人任务号
12；`--max-actions 3` 会等最后一个动作的 PC 复位完成后再退出。

`-u` 用于立即输出握手事件。默认持续运行，按 `Ctrl+C` 后清理脚本负责的 PLC→PC
仿真信号。自动完成指定数量动作后退出可增加：

```text
--max-actions 3
```

除非需要保留现场进行人工排查，否则不要使用 `--keep-state-on-exit`。

## 5. Bridge + Edge 后台一键启动

以下代码块可以整体执行。它只启动 Bridge 和 Edge；前端和握手仿真器仍建议单独启动。

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

mkdir -p runtime/ideawit-e2e/logs

export PYTHONPATH="/home/changjunhan/Uni-Lab-Core/Uni-Lab-OS:/home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab${PYTHONPATH:+:${PYTHONPATH}}"

nohup /home/changjunhan/.micromamba/envs/unilab/bin/python \
  deployment/local_bridge_entrypoint.py \
  --host 127.0.0.1 \
  --schedule-port 8892 \
  --api-port 8015 \
  --execution-http-url http://127.0.0.1:18003 \
  --journal-path runtime/ideawit-e2e/quick-debug.sqlite3 \
  --profile szlab_poly_studio/profiles/default/package.yaml \
  > runtime/ideawit-e2e/logs/bridge.log 2>&1 &
SZLAB_BRIDGE_PID=$!
printf '%s\n' "${SZLAB_BRIDGE_PID}" > runtime/ideawit-e2e/bridge.pid

sleep 2

export UNILABOS_RUNTIME_DB="$(pwd)/runtime/ideawit-e2e/edge-runtime-$(date +%Y%m%d-%H%M%S).sqlite3"

nohup /home/changjunhan/.micromamba/envs/unilab/bin/unilab \
  --graph /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/deployment/graphs/szlab-ideawit-sim.json \
  --config /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/deployment/local_config.py \
  --working_dir /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/runtime/ideawit-e2e \
  --devices /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab/szlab_poly_studio \
  --external_devices_only \
  --backend ros \
  --app_bridges websocket fastapi \
  --port 18003 \
  --schedule_addr ws://127.0.0.1:8892/api/v1/ws/schedule \
  --disable_browser \
  --skip_env_check \
  > runtime/ideawit-e2e/logs/edge.log 2>&1 &
SZLAB_EDGE_PID=$!
printf '%s\n' "${SZLAB_EDGE_PID}" > runtime/ideawit-e2e/edge.pid

printf 'bridge pid=%s, edge pid=%s\n' "${SZLAB_BRIDGE_PID}" "${SZLAB_EDGE_PID}"
```

实时查看：

```bash
tail -f runtime/ideawit-e2e/logs/bridge.log
```

```bash
tail -f runtime/ideawit-e2e/logs/edge.log
```

## 6. 启动健康检查

```bash
curl --fail-with-body -sS \
  http://127.0.0.1:8015/api/v1/runtime/capabilities | jq .

curl --fail-with-body -sS \
  -o /dev/null \
  -w 'edge_runtime_actions_http=%{http_code}\n' \
  http://127.0.0.1:18003/internal/v1/runtime-actions

curl --fail-with-body -sS \
  -o /dev/null \
  -w 'frontend_http=%{http_code}\n' \
  http://127.0.0.1:5173/

ss -ltnp | rg ':(5173|8015|8892|18003)\b'
```

期望 Edge 和前端均返回 HTTP 200。Edge 初始化期间
`/internal/v1/runtime-actions` 可能短暂返回 503，等 `Host node initialized` 后重试。

## 7. 当前七个握手动作

| 序号 | 工作流动作 | PC→PLC 触发 | 仿真器响应 |
| --- | --- | --- | --- |
| 1 | `submit_place_to_s04` | 位置、任务号 7、任务写入完成 | 完成码 7、目标位传感器置 True |
| 2 | `run_stirring` | S04 工艺选择、参数写入完成 | 允许信号拉低、加工完成置 True、响应复位 |
| 3 | `submit_pick_from_s04` | 位置、任务号 8、任务写入完成 | 完成码 8、目标位传感器置 False |
| 4 | `take_photo` | 当前驱动没有独立启动写入 | 保持 `S05加工完成=True`、`S05拍照结果=1` |
| 5 | `run_solvent_addition` | S06 工艺选择、添加量、参数写入完成 | 产生新的 `False→True` 加工完成周期并响应复位 |
| 6 | `submit_place_to_s06` | 任务号 11、任务写入完成 | 完成码 11、S06 烧杯传感器置 True |
| 7 | `submit_pick_from_s06` | 任务号 12、任务写入完成 | 完成码 12、S06 烧杯传感器置 False |

S05 当前只能用既有完成/结果节点模拟。它不是完整的“启动—加工—完成—复位”握手；
在 PLC 接口增加明确的 S05 启动与复位变量之前，不应伪造不存在的节点。

## 8. 全部工作流的启动先决条件

完整节点名和期望值以握手脚本的 `list` 输出为准。当前摘要如下：

| 工作流 | 启动前条件 |
| --- | --- |
| `szlab_magnetic_stirring_workflow` | 对应 S04 工位允许加工，完成信号为 False |
| `szlab_photoshotting_workflow` | S05 加工完成为 True，拍照结果为 1 |
| `szlab_robot_action_workflow` | Robot Home、允许写入、完成码 0，S04 目标位为空 |
| `s04_robot_stirring_workflow` | 机械臂公共条件、S04 目标位为空、S04 允许加工且未完成 |
| `s06_robot_workflow` | 机械臂公共条件、机器人放料前 S06 无烧杯、S06 准备/允许、储液瓶在位 |
| `s07_robot_workflow` | 机械臂公共条件，S071/S072 目标位为空 |
| `szlab_s07_solid_addition_workflow` | S07 原点、允许加工、完成码 0、二维码节点和配方文件有效 |
| `s08_cap_workflow` | S08 原点、允许加工、完成码 0、瓶盖缓存和样品 ID 有效 |
| `szlab_s09_pipetting_workflow` | 工站状态 2、完成码 0、液体余量大于 0、枪头参数合法 |
| `szlab_stack_s05_s06_workflow` | 堆栈可读、S05 OK、S06 烧杯/储液瓶在位、S06 准备/允许 |
| `szlab_mixer_workflow` | S06 条件满足；不跳过机械臂时必须配置两个机械臂位置 |
| `szlab_mixer_pump_production` | 同上，S06 完成信号必须从 False 开始新周期 |

默认 `all` 场景为了直接测试 S06 泵动作，会初始化 `S06` 烧杯在位为 True。
完整测试 `s06_robot_workflow` 时必须增加
`--workflow s06_robot_workflow`；该场景会初始化为空，并由任务号 11/12 驱动
烧杯传感器的 False→True→False 状态变化。

## 9. 提交已编译的 S04 三动作工作流

先保证握手仿真器正在运行，然后在另一个终端执行：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

jq -n \
  --slurpfile revision runtime/workflows/s04_robot_stirring_workflow.json \
  '{
    source: {
      format: "workflow_revision_v2",
      revision: $revision[0]
    },
    parameters: {
      position: 1
    }
  }' |
curl --fail-with-body -sS \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  http://127.0.0.1:8015/api/v1/runtime/runs
```

返回示例：

```json
{
  "id": "584c86ab320b4d6a86ceff43798e14cb",
  "status": "pending"
}
```

该工作流应依次出现：

```text
submit_place_to_s04: accepted -> completed -> reset
run_stirring: accepted -> completed -> reset
submit_pick_from_s04: accepted -> completed
```

## 10. 编译并提交 S05/S06 联合工作流

这个命令通过 Bridge 的 authoring compiler 编译现有 Python 工作流，不手工补充 JSON 节点：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

set -o pipefail

jq -Rs \
  '{
    base_revision_id: "python-v1",
    python_source: .,
    source_uri: "workflows/stack_s05_s06.py"
  }' \
  szlab_poly_studio/workflows/stack_s05_s06.py |
curl --fail-with-body -sS \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  http://127.0.0.1:8015/api/v1/authoring/compile |
jq '{
  source: {
    format: "workflow_revision_v2",
    revision: .candidate.canonical_ir
  }
}' |
curl --fail-with-body -sS \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  http://127.0.0.1:8015/api/v1/runtime/runs
```

该工作流应完成：

```text
szlab_poly_plc.get_stack_status
szlab_mixer_photoshotting.take_photo
szlab_mixer_pump.run_solvent_addition
```

## 11. 查询运行状态、节点与事件

先记录启动接口返回的 `id`：

```bash
SZLAB_RUN_ID='替换为实际运行ID'
```

查询运行：

```bash
curl --fail-with-body -sS \
  "http://127.0.0.1:8015/api/v1/runtime/runs/${SZLAB_RUN_ID}" | jq .
```

查询节点：

```bash
curl --fail-with-body -sS \
  "http://127.0.0.1:8015/api/v1/runtime/runs/${SZLAB_RUN_ID}/nodes" | jq .
```

查询事件：

```bash
curl --fail-with-body -sS \
  "http://127.0.0.1:8015/api/v1/runtime/runs/${SZLAB_RUN_ID}/events?after_seq=0" | jq .
```

正常终态：

```text
run.status = completed
每个执行节点 state = success
```

## 12. 调试方法

### 12.1 Bridge 正常、Edge 未接入

表现：

- Bridge API 可访问；
- 新运行长期停留在 `pending`；
- Edge action catalog 不可用或返回 503。

检查：

```bash
curl -i http://127.0.0.1:18003/internal/v1/runtime-actions
tail -n 200 runtime/ideawit-e2e/logs/edge.log
```

重点确认：

- Edge 使用 `8892`，不是默认 `8890`；
- Bridge 使用 `--execution-http-url http://127.0.0.1:18003`；
- Edge 日志出现 `Host node ready signal published`。

### 12.2 OPC UA 连接失败

表现：

```text
client connected!
```

没有出现，或者握手器在 `adapter.connect()` 处失败。

检查：

- URL 是否为 `opc.tcp://opcua.ideawit.com:4855/xuse_sim`；
- 仿真服务器是否在线；
- `szlab_plc_0730.csv` 是否已经导入；
- NodeId 前缀是否仍为 `ns=4;s=上位机通讯|`；
- 服务器变量类型和写权限是否与 CSV 一致。

不要通过修改驱动或工作流 JSON 来绕过缺失节点。应修正仿真服务器的 CSV 导入。

### 12.3 握手器初始化出现 FAIL

`serve` 会在写入后逐项读回。如果任何项目读回失败，它会拒绝进入握手循环。

常见原因：

- CSV 未导入或节点名不一致；
- 仿真服务器节点只读；
- 变量的 OPC UA VariantType 与写入值不一致；
- 同时启动了两个握手器，互相覆盖状态。

建议先运行：

```bash
/home/changjunhan/.micromamba/envs/unilab/bin/python \
  scripts/szlab_workflow_handshake.py check \
  --position 1 \
  --pump 1
```

注意：握手器退出后会把仿真输出恢复为 False/0，因此退出后的 `check` 出现 FAIL
通常表示“当前不满足工作流启动条件”，不等于 OPC UA 连接失败。

### 12.4 S04 机械臂卡住

检查以下变量：

```text
Robot_Home
Robot_任务允许写入
Robot_任务写入完成
任务号
Robot_任务完成
S04取放料编号
传感器状态_上位机[2].NO[10]   # position=1
```

正常新任务开始前：

```text
Robot_Home=True
Robot_任务允许写入=True
Robot_任务写入完成=False
Robot_任务完成=0
```

### 12.5 S04 磁搅卡住

以 position 1 为例：

```text
S041允许加工=True
S041加工完成=False
S041磁搅工艺选择=1/2/3
S041参数写入完成=True
```

仿真器检测到参数写入后会产生新的完成周期。若开始前完成信号已经是 True，
驱动的 `wait_new_cycle_done` 不会把旧完成信号当作新完成。

### 12.6 S06 泵卡住

检查：

```text
S06准备信号=True
S06允许加工=True
S06加工完成=False
传感器状态_上位机[3].NO[1]=True
传感器状态_上位机[4].NO[12]=True   # pump=1
```

开始后应看到：

```text
S06工艺选择=1/2/3
S06参数写入完成=True
S06加工完成: False -> True
```

### 12.7 设备动作物理成功但 DAG 判失败

如果事件里设备回执 `success=true`，但节点提示：

```text
output 'success' is not declared by the action contract
```

说明 Edge 仍在运行旧版 OS 代码。当前实现只把 action contract 声明过的字段投影为工作流
输出，完整设备回执保留在终态诊断信息中。更新代码后必须重启 Edge。

### 12.8 查看日志

交互式 Edge 日志：

```text
runtime/ideawit-e2e/logs/<启动时间>.log
runtime/ideawit-e2e/logs/ws_comm_<启动时间>.log
```

后台启动日志：

```text
runtime/ideawit-e2e/logs/bridge.log
runtime/ideawit-e2e/logs/edge.log
```

Bridge journal：

```text
runtime/ideawit-e2e/quick-debug.sqlite3
```

Edge 默认运行 journal 位于运行用户的：

```text
~/.unilabos/runtime.sqlite
```

本地反复联调时推荐为每次 Edge 启动显式设置新的 journal，避免上次异常退出遗留的动作锁
让新工作流一直显示“等待中”：

```bash
export UNILABOS_RUNTIME_DB="$(pwd)/runtime/ideawit-e2e/edge-runtime-$(date +%Y%m%d-%H%M%S).sqlite3"
```

这也是第 5 节一键启动命令采用的方式。journal 仍会保存在仓库的 `runtime/` 目录中，便于
复盘。

## 13. 停止和清理

推荐顺序：

1. 等当前工作流进入终态，或通过 Runtime API 请求取消；
2. `Ctrl+C` 停止握手器，让它恢复仿真信号；
3. 停止 Edge；
4. 停止 Bridge；
5. 停止前端。

后台模式停止前先核对 PID 对应的命令：

```bash
ps -fp "$(sed -n '1p' runtime/ideawit-e2e/edge.pid)"
ps -fp "$(sed -n '1p' runtime/ideawit-e2e/bridge.pid)"
```

确认无误后：

```bash
kill -TERM "$(sed -n '1p' runtime/ideawit-e2e/edge.pid)"
kill -TERM "$(sed -n '1p' runtime/ideawit-e2e/bridge.pid)"
```

不要对仓库目录、运行目录或用户目录执行递归删除。SQLite journal 和日志用于复盘，
默认应保留。

## 14. 回归测试

SZLab：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

/home/changjunhan/.micromamba/envs/unilab/bin/python -m py_compile \
  scripts/szlab_workflow_handshake.py

/home/changjunhan/.micromamba/envs/unilab/bin/python -m pytest -q
```

Uni-Lab-OS：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-OS

/home/changjunhan/.micromamba/envs/unilab/bin/python -m pytest -q \
  tests/scheduler \
  tests/runtime

/home/changjunhan/.micromamba/envs/unilab/bin/python -m pytest -q \
  tests/app \
  --ignore=tests/app/test_workflow_authoring_api.py
```

当前已验证结果：

```text
Uni-Lab-SZLab: 31 passed
Uni-Lab-OS scheduler/runtime: 146 passed
Uni-Lab-OS app（排除缺失的外部模板 fixture）: 130 passed
```

## 15. 已验证的联调记录

2026-07-30 使用本文档端口和远端仿真服务器完成：

| Run ID | 工作流 | 结果 |
| --- | --- | --- |
| `584c86ab320b4d6a86ceff43798e14cb` | S04 放置 → 磁搅 → 取回 | `completed`，3 节点全部 success |
| `cb85746b54194e419531a447df4b8617` | 堆栈读取 → S05 拍照 → S06 加液 | `completed`，3 节点全部 success |

验收标准：

- 前端、Bridge、Edge 健康检查通过；
- Edge 内只有 `szlab_poly_plc` 直接配置 OPC UA；
- 握手器不创建节点；
- 五个首批动作均有真实工作流覆盖；
- 运行终态为 `completed`；
- 所有执行节点为 `success`；
- 握手器退出后完成安全清理。
