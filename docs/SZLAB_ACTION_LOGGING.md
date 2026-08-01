# SZLab 动作与 PLC 等待日志

SZLab 设备动作默认在 Edge 日志中输出结构化、可检索的调试信息。该功能只修改
Uni-Lab-SZLab 设备包，不修改 Uni-Lab-OS。

## 日志标记

| 标记 | 内容 |
| --- | --- |
| `SZLAB-ACTION` | 每个 `@action` 的动作名称、输入参数、耗时、结果或失败原因 |
| `SZLAB-STEP` | 设备内部业务步骤，例如等待烧杯、允许加工、机器人握手或参数清零 |
| `SZLAB-PLC-CALL` | 业务设备通过唯一 `szlab_poly_plc` 发起的跨设备调用 |
| `SZLAB-PLC-WAIT` | 等待变量、期望值、实际值变化、持续等待、成功或超时 |
| `SZLAB-PLC-WRITE` | 写入变量、值、NodeId、尝试次数、耗时和失败异常 |
| `SZLAB-PLC-READ` | 读取失败及其异常；成功读取仅在 DEBUG 级别记录，避免属性轮询刷屏 |
| `SZLAB-HTTP` | S1 HTTP 动作等待的接口、超时、响应状态和网络异常 |

密码、Token、Secret、Authorization 等字段会显示为 `***`。长列表和字典会截断，
防止单条日志过大。

## 示例

```text
[SZLAB-ACTION] START trace=38a55f16b2 action=SzlabMixerPumpDevice.run_solvent_addition params={'pump': 1, 'volume': 8, ...}
[SZLAB-STEP] WAIT trace=38a55f16b2 action=SzlabMixerPumpDevice.run_solvent_addition description=等待 S06 允许加工 variable=S06允许加工 expected=True timeout=300.000s
[SZLAB-PLC-CALL] START trace=38a55f16b2 action=SzlabMixerPumpDevice.run_solvent_addition plc_device=szlab_poly_plc operation=wait_variable_equal ...
[SZLAB-PLC-WAIT] OBSERVED trace=- action=- variable=S06允许加工 node_id=ns=4;s=上位机通讯|S06允许加工 expected=True actual=False elapsed=0.081s
[SZLAB-PLC-WAIT] SUCCESS trace=- action=- variable=S06允许加工 node_id=ns=4;s=上位机通讯|S06允许加工 expected=True actual=True elapsed=5.132s
[SZLAB-PLC-WRITE] START trace=- action=- variable=S06工艺选择 node_id=ns=4;s=上位机通讯|S06工艺选择 value=1 attempts=3
[SZLAB-PLC-WRITE] SUCCESS trace=- action=- variable=S06工艺选择 node_id=ns=4;s=上位机通讯|S06工艺选择 value=1 attempt=1/3 elapsed=0.047s
[SZLAB-ACTION] SUCCESS trace=38a55f16b2 action=SzlabMixerPumpDevice.run_solvent_addition elapsed=18.245s result='S06 泵 1 加液流程完成'
```

如果等待失败，会包含最后一次实际值：

```text
[SZLAB-PLC-WAIT] TIMEOUT ... variable=S06加工完成 expected=True last_actual=False elapsed=300.041s
[SZLAB-ACTION] FAIL ... reason='S06 加工完成等待超时'
```

如果写入失败，会包含变量、写入值、NodeId、重试次数和原始异常：

```text
[SZLAB-PLC-WRITE] FAIL ... variable=S06参数写入完成 ... value=True attempt=3/3 cause=TimeoutError: timed out
```

`trace` 用于关联同一业务动作的 `SZLAB-ACTION`、`SZLAB-STEP` 和
`SZLAB-PLC-CALL`。统一 PLC 设备在独立 ROS 执行线程中处理实际 OPC UA 请求，因此底层
`SZLAB-PLC-WAIT/WRITE/READ` 可能显示 `trace=-`；此时按变量名、操作名和相邻时间定位。

## 实时查看

后台启动 Edge 时：

```bash
cd /home/changjunhan/Uni-Lab-Core/Uni-Lab-SZLab

tail -f runtime/ideawit-e2e/logs/edge.log \
  | rg --line-buffered 'SZLAB-(ACTION|STEP|PLC-CALL|PLC-WAIT|PLC-WRITE|PLC-READ|HTTP)'
```

查看某次动作的完整链路：

```bash
rg 'trace=38a55f16b2|S06加工完成|S06工艺选择' \
  runtime/ideawit-e2e/logs/edge.log
```

只看失败：

```bash
rg 'SZLAB-.*(FAIL|TIMEOUT|ERROR)' \
  runtime/ideawit-e2e/logs/edge.log
```

交互式启动 Edge 时这些日志会同时直接显示在终端。

## 等待日志频率

等待开始时打印一次；实际值变化时打印一次；值没有变化时每 10 秒打印一次
`STILL`；成功或超时时再打印一次。普通成功读取保持 DEBUG 级别，心跳写入也保持
DEBUG 级别，避免掩盖真正的动作日志。
