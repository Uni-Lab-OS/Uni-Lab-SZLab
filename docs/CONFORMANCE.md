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

`check-package.sh` 当前使用 OS 的旧 `--devices` 兼容入口。Issue #147 的 OS delivery 完成后，
必须增加 `unilab package inspect --path .`、`unilab --workspace . --check_mode` 以及 workspace /
clean-wheel Catalog 一致性检查。
