# SZLab 领域设备包一致性合同

## 仓库边界

- 仓库根是唯一 Python distribution root 和目标 OS workspace root；
- 根 `pyproject.toml` 的 distribution 是 `szlab-poly-studio`；
- 唯一常规顶层 import package 是 `szlab_poly_studio`；
- 不允许 `packages/` 中间层或第二个领域 import package；
- AI4C 由独立的同级仓库维护。

## 发现边界

- 顶层定义只来自 `@device`、`@resource`、`@workflow_definition`；
- 动作、状态和订阅装饰器归入所属设备；
- 模型由同一个设备/资源装饰器绑定；
- `deployment/`、`tests/`、`docs/`、`migration/` 不属于扫描根；
- 静态发现不得 import 驱动、实例化设备或连接硬件。
- Graph 是实例拓扑、连接参数与激活选择的唯一权威来源，不使用运行时 Profile。

## Workflow authoring 边界

- 新 Workflow 遵循 Core 的
  [`Workflow Python 写法规范`](https://github.com/Uni-Lab-OS/Uni-Lab-Core/blob/main/docs/guides/python-workflow-authoring-standard.md)；
- 新材料链必须从 Action 参数起使用 `ResourceSlot`，不能只靠 position/sample_id 和控制边推断；
- `szlab_poly_studio/workflows/s06_material.py` 是当前可发布的单工作流参考实现；
- `docs/examples/workflow_authoring/*_target.py` 只描述 C1 目标合同，不进入 `package.yaml`。

## 资产边界

- 设备资产位于 `devices/<device_id>/models/`；
- 资源资产位于 `resources/<resource_id>/models/`；
- 模型入口相对声明 Python 文件解析，并且必须位于 import package 内；
- wheel 必须携带 YAML、Xacro、URDF、mesh 和 texture 等完整依赖闭包；
- 运行日志、数据库、现场标定和凭据不得进入 wheel。

## 本地检查

```bash
python -m pip install -e . --no-deps
./scripts/check-package.sh
python -m pytest
./scripts/build-package.sh
```

`check-package.sh` 执行 `package inspect --path .` 与 `--workspace . --check_mode`；
`build-package.sh` 通过 package manager 构建并审计 clean wheel。自动测试同时验证 workspace /
clean-wheel Catalog 一致性。
