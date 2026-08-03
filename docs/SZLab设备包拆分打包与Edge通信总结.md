# SZLab 设备包拆分、打包与 Edge 通信总结

## 1. 一般设备如何从 Uni-Lab-OS 分离为领域设备包

### 1.1 先确定边界

设备包应拥有设备驱动、动作、资源定义、工作流、协议表和模型资产；Uni-Lab-OS
保留通用装饰器、Registry、调度、通信抽象、PackageCatalog 编译和运行时。拆分时禁止把 OS
内部任意模块整段复制进设备包，只有确实属于领域设备且无法复用的适配器才进入 `common/`。

### 1.2 建立根单包仓库

```text
repository root = Python distribution root = OS workspace root
```

根 `pyproject.toml` 直接构建唯一 import package。SZLab 使用：

```text
distribution: szlab-poly-studio
import package: szlab_poly_studio
class namespace: community.szlab_poly_studio
```

一个包可以定义多个设备；设备身份来自各自的 `@device(id=...)`，不是来自 distribution 名。

### 1.3 迁移步骤

1. 将驱动类迁到 `devices/<device_id>/device.py`；
2. 保留 `@device`、`@action`、`@topic_config`、`@subscribe` 等装饰器；
3. 将资源工厂迁到 `resources/` 并保留 `@resource`；
4. 将 Python 工作流迁到 `workflows/` 并保留 `@workflow_definition`；
5. 将 CSV、JSON、Xacro、mesh、texture 放到拥有者目录；
6. 去除 OS 私有绝对 import、硬编码本机路径、凭据和运行数据；
7. 配置 package-data，构建 clean wheel 并验证静态发现结果；
8. 在 Graph 中写入实例拓扑和连接参数；只有 Graph 选中设备后，运行时才允许 import 和连接硬件。

AI4C 已作为同级 `Uni-Lab-AI4C/` 独立根单包，不再和 SZLab 组成 monorepo。

## 2. 设备包目录与包含的信息

SZLab 当前结构：

```text
Uni-Lab-SZLab/
├── pyproject.toml                 # distribution 身份、依赖、package-data
├── szlab_poly_studio/
│   ├── devices/<device_id>/
│   │   ├── device.py              # @device 与动作
│   │   ├── sensors.py             # 可选协议语义
│   │   ├── *.csv / *.json         # 协议表、静态参数
│   │   └── models/                # 设备专属模型闭包
│   ├── resources/                 # @resource、warehouse、deck、资源模型
│   ├── workflows/                 # @workflow_definition
│   ├── common/                    # 本包内部共享实现
│   └── __init__.py
├── deployment/graphs/             # 实例图；不属于装饰器扫描根
├── tests/                          # Catalog、Graph、工作流、资产和 wheel 测试
├── scripts/                        # build/check/start 辅助入口
├── docs/
└── migration/                      # 可审计历史输入，不参与运行时发现
```

不同层次的信息含义：

- `@device/@resource/@workflow_definition`：稳定类型身份和静态能力；
- 从属装饰器：设备的动作、状态、订阅和调度属性；
- Graph：本次部署的实例 ID、位置、连接参数和选择结果；
- `models/`：随设备/资源类型发布的可移植模型，不保存现场标定；
- runtime：日志、数据库、缓存，不进入 wheel 和 Git。

## 3. 设备包如何与 Uni-Lab-OS Edge 通信

### 3.1 发现与运行分离

目标启动方式：

```bash
unilab --workspace . -g deployment/graphs/szlab-local-debug.json
```

OS 读取根 `pyproject.toml`，AST 扫描唯一 import package，编译统一 PackageCatalog。这个阶段不
import 驱动、不实例化设备、不连接 PLC。Graph 选择本次运行需要的实例；选中后才加载对应
Python 类。

仓库检查入口为：

```bash
python -m unilabos.app.main package inspect --path .
unilab --workspace . --check_mode
```

2.5D 模型使用显式绑定的 `models/shape.yml`，避免兼容加载器把设备子树内的 `*.yaml`
误判成旧注册表。目录已经符合 workspace 合同，但不能把兼容命令当成最终 package manager。

### 3.2 Edge 内的通信层次

```text
设备包装饰器/驱动
        │
        ▼
Registry + PackageCatalog
        │
        ├── ROS device action / topic / subscription
        ├── local bridge authoring/runtime API
        └── Edge asset API（模型）
        │
        ▼
PLC / HTTP 设备 / 前端 / 调度器
```

SZLab 的 PLC 结构是“一条实际 PLC 连接 + 多个业务设备”：

- `szlab_poly_plc` 拥有 OPC UA 连接和通用读写动作；
- robot、S04-S09 等业务设备通过 `PLCActionGateway` 调用 PLC 设备动作；
- 业务设备不各自建立第二条 OPC UA 连接；
- Graph 中用 `plc_device_id: szlab_poly_plc` 绑定实例；
- 测试图默认 `auto_connect: false`。

### 3.3 工作流与 Graph

Python 工作流通过 `device("instance_id").action(...)` 描述调用，由 OS AST 编译成 Canonical
workflow；不使用 `eval/exec`。工作流声明随 Catalog 交付，Graph 决定具体实例、拓扑与连接
参数；local bridge 与 Edge 消费同一份 PackageCatalog，不维护另一套扫描器。

### 3.4 模型通信

模型通过 `@device/@resource(model=...)` 进入 Catalog。Edge 根据声明文件解析相对路径、校验
资产闭包并返回受控 URL；Xacro 的 `mesh_path` 由 Edge 注入。详细规范见
[`设备包3D模型存储规范.md`](设备包3D模型存储规范.md)。

## 4. 验证命令

```bash
python -m pip install -e . --no-deps
./scripts/check-package.sh
python -m pytest
./scripts/build-package.sh
```

验收至少覆盖：唯一根包、Catalog 发现数量、Graph 引用闭合、工作流编译、模型相对路径、wheel
资产闭包、workspace/clean-wheel Catalog 一致、无跨包 import、默认不连硬件。
