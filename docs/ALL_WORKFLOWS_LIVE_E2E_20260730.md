# SZLab 全工作流远端 OPC UA 联调结果（2026-07-30）

## 结论

新版前端、Local Bridge、Edge、统一 PLC 通信模块和独立握手器已连接
`opc.tcp://opcua.ideawit.com:4855/xuse_sim` 完成 12 个 SZLab Python 工作流的逐一联调。

- 结果：`12/12 passed`
- 节点结果：全部 `success`
- 截图：每个工作流 3 张，共 36 张，分为运行中、完成态和事件流
- OPC UA NodeId 前缀：`ns=4;s=上位机通讯|`
- 前端：`http://127.0.0.1:5173`
- Bridge：`http://127.0.0.1:8015`
- Edge：`http://127.0.0.1:18003`
- Schedule：`ws://127.0.0.1:8892/api/v1/ws/schedule`

机器可读总结果见
[`result-summary.json`](screenshots/all-workflows-live-e2e-20260730/result-summary.json)。

## 工作流结果

| # | 工作流源码 | Run ID | 节点结果 | 截图 |
| --- | --- | --- | --- | --- |
| 1 | `magnetic_stirring.py` | `572f7d649302435990842cf955c838cc` | 1/1 success | [目录](screenshots/all-workflows-live-e2e-20260730/01-szlab_magnetic_stirring_workflow/) |
| 2 | `photoshotting.py` | `c346d965854643d8be37a9816e71d3ec` | 1/1 success | [目录](screenshots/all-workflows-live-e2e-20260730/02-szlab_photoshotting_workflow/) |
| 3 | `robot_action.py` | `291dfadd521c4c62aaa2ddcfc0b820ec` | 2/2 success | [目录](screenshots/all-workflows-live-e2e-20260730/03-szlab_robot_action_workflow/) |
| 4 | `s04_robot_stirring.py` | `6bf8156a03c54c589124c2f47b254dd2` | 3/3 success | [目录](screenshots/all-workflows-live-e2e-20260730/04-s04_robot_stirring_workflow/) |
| 5 | `s06_robot.py` | `908ef5f67baf481abae1fc0d0478e8b4` | 3/3 success | [目录](screenshots/all-workflows-live-e2e-20260730/05-s06_robot_workflow/) |
| 6 | `s07_robot.py` | `d519c5597a59486d838a28dab41e554e` | 3/3 success | [目录](screenshots/all-workflows-live-e2e-20260730/06-s07_robot_workflow/) |
| 7 | `s07_solid_addition.py` | `3543dd3cee0747ada4e76e99c4e52297` | 3/3 success | [目录](screenshots/all-workflows-live-e2e-20260730/07-szlab_s07_solid_addition_workflow/) |
| 8 | `s08_cap.py` | `bdf91a4752734197a144ca8fd5cb6853` | 2/2 success | [目录](screenshots/all-workflows-live-e2e-20260730/08-s08_cap_workflow/) |
| 9 | `s09_pipetting.py` | `70b0f5ef4a2f4df6babbb1722cfc8c2b` | 4/4 success | [目录](screenshots/all-workflows-live-e2e-20260730/09-szlab_s09_pipetting_workflow/) |
| 10 | `stack_s05_s06.py` | `a4135ccdad5b42e5a935aeff0aac6b1b` | 3/3 success | [目录](screenshots/all-workflows-live-e2e-20260730/10-szlab_stack_s05_s06_workflow/) |
| 11 | `szlab_mixer.py` | `215272bc84b04633a04585621fa112a9` | 1/1 success | [目录](screenshots/all-workflows-live-e2e-20260730/11-szlab_mixer_workflow/) |
| 12 | `szlab_mixer_pump_production.py` | `9d279a874e0e4c9581c37fca9fcf587a` | 1/1 success | [目录](screenshots/all-workflows-live-e2e-20260730/12-szlab_mixer_pump_production/) |

每个目录包含：

- `01-running.png`：工作流正在运行；
- `02-completed.png`：全部节点执行成功；
- `03-events.png`：运行事件流；
- `compiled-workflow.json`：前端编译后的工作流；
- `run-created.json`、`run-progress.json`、`run-final.json`、`run-timeline.json`；
- `handshake.log`：握手器对仿真服务器的变量交互；
- `result.json`：该工作流的机器可读结论。

汇总日志位于
[`logs/`](screenshots/all-workflows-live-e2e-20260730/logs/)。

## 联调中确认并修正的问题

1. Edge 必须使用独立、干净的运行 journal。旧的
   `~/.unilabos/runtime.sqlite` 中残留的动作锁会让新任务停在等待状态。本次通过
   `UNILABOS_RUNTIME_DB` 指向本次联调专用 SQLite 文件。
2. 远端 OPC UA 偶发超时或 `BadNodeIdUnknown` 时，统一 PLC 客户端会重连并有限重试；
   所有设备仍经同一个 PLC 通信模块读写，没有新增每设备 OPC UA 连接。
3. 完成信号不能在 Edge 读到新周期的 `False` 基线前立即变成 `True`。握手器默认
   `--process-delay` 已改为 5 秒。`stack_s05_s06.py` 随后以 5 秒延迟自动复跑成功，
   不需要人工修改变量。
4. S07 固体投料只复位该动作实际使用的既有变量，避免无关批量写入放大远端通信压力；
   没有在驱动、JSON 或仿真服务器中补充节点。
5. 纯泵工作流使用 `skip_robot=True`，符合工作流中不包含机器人动作节点的结构。

## 回归检查

- Python 测试：`48 passed`
- Ruff：通过
- SZLab 设备包注册表：`25/25` 通过，10 个设备类型解析成功
- Node E2E 脚本语法：通过
- Shell 启动脚本语法：通过
- 12 个工作流的 `result.json`：全部 `outcome=passed`

## 已知非阻断日志

Edge 在无云端登录信息的本地模式仍会记录云端启动配置/物料上传的 401；当前 Deck
资源转换还会记录 `Deck.__init__() got an unexpected keyword argument 'setup'`。这两类日志
没有阻止本地设备注册、动作调度或本次 12 个工作流完成。Edge 退出时后台属性发布线程还可能
记录一次 ROS publisher context 已关闭；该日志发生在所有工作流进入终态并正常发送
`normal_exit` 之后。

## 复现命令

服务启动后执行：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

UNILAB_HANDSHAKE_PROCESS_DELAY=5.0 \
  ./scripts/capture-all-workflows-live-e2e.sh
```

脚本会逐个导入 Python 工作流，通过前端启动运行，为每个工作流独立启动对应握手场景，
等待终态并输出截图和 JSON 证据。
