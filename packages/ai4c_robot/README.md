# AI4C robot device package

外部包入口为 `ai4c_robot/`，包含 AI4C PLC、机械臂和完整搬运调试 Python 工作流。

检查：

```bash
unilab --check_mode --devices ./ai4c_robot --external_devices_only
```

本地部署图以 `auto_connect: false` 创建 PLC；只有受控真机配置才能启用 OPC UA 连接。
