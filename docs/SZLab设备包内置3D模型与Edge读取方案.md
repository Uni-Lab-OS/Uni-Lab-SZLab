# SZLab 设备包内置 3D 模型与 Edge 读取方案

> 整理日期：2026-07-29  
> 目标：安装或引用 SZLab 设备包时，设备实现、Profile 和 3D 模型作为同一个版本化单元一起进入 Uni-Lab Edge  
> 结论：保留 XACRO 和 `mesh_path`，但把 `mesh_path` 从“写死的 Uni-Lab-OS 目录”改成“Edge 从已安装设备包解析出的模型资源根”

## 1. 结论先行

`mesh_path` 对这个需求非常有用，而且现有前端已经在使用它。

但需要区分两件事：

1. `mesh_path` 只是 XACRO 模型内部解析 STL、YAML、子 XACRO 等资源的“根地址”。
2. 它本身不能让 Edge 自动发现外部设备包里的模型。

因此完整方案应当是：

```text
设备 wheel
├── Python 驱动
├── Profile / Device Spec
├── 3D 模型资源
├── 模型清单 manifest.yaml
└── unilabos.model_bundles 安装入口
          │
          ▼
Edge 启动时发现模型包
          │
          ├── 校验模型清单和全部相对路径
          ├── 建立 device/resource identity → model key 映射
          ├── 为浏览器生成同源 HTTP URL
          └── 为 ROS/RViz/MoveIt 解析本地文件路径
```

推荐的格式策略不是“全部只用一种格式”，而是按模型用途选择：

| 场景 | 推荐格式 | 原因 |
| --- | --- | --- |
| 有关节、link、末端执行器、安装点的设备 | XACRO 作为权威描述 | 支持参数、宏、URDF link/joint 和 ROS 工具链 |
| 无关节的静态设备或整个工作站外壳 | GLB 优先 | 浏览器加载快、单文件、材质和纹理完整 |
| MoveIt/碰撞检测 | XACRO/URDF + 低面数 collision mesh | 需要 link/joint 和简化碰撞几何 |
| 简单物料、瓶、枪头等 | GLB 或低面数 STL | 模型简单，不需要 XACRO 宏 |

对 SZLab，建议采用混合模式：

```text
XACRO / URDF   = 运动学和装配关系的权威来源
GLB            = 浏览器静态展示的优化表示
STL            = 视觉或碰撞子网格，不作为整个模型包的发现入口
```

第一阶段为了最小改动，可以继续直接让前端加载 XACRO。现有前端路径约定和
`mesh_path` 已经能够支持这一方式。

---

## 2. 当前实现与目标之间的差距

### 2.1 当前模型固定属于 Uni-Lab-OS

目前本地模型登记逻辑位于：

- [`material_models.py`](../../Uni-Lab-OS/unilabos/app/local_bridge/material_models.py)

其中：

- `_MODEL_DEFINITIONS` 写死了 5 组模型；
- 默认模型根固定为 `unilabos/device_mesh`；
- `MaterialModelRegistry` 只在这个固定根目录下解析文件；
- 外部 wheel 中即使包含模型，也不会被当前 Registry 自动发现。

当前默认根目录的本质是：

```python
package_root = Path(__file__).resolve().parents[2]
asset_root = package_root / "device_mesh"
```

这意味着现有逻辑只适用于：

```text
unilabos/
└── device_mesh/
```

而不适用于：

```text
site-packages/
└── szlab_poly_studio/
    └── models/
```

### 2.2 当前 HTTP 接口已经可以提供模型文件

本地 Edge 已有：

```text
GET /api/v1/material-models
GET /api/v1/material-models/assets/{asset_path}
```

对应代码位于：

- [`local_api.py`](../../Uni-Lab-OS/unilabos/app/local_bridge/local_api.py)

当前资源接口会：

1. 把 URL 中的相对路径交给模型 Registry；
2. 校验解析结果没有越出固定 `asset_root`；
3. 使用 `FileResponse` 返回 XACRO、YAML、STL 等文件；
4. 不把宿主机绝对路径暴露给浏览器。

这套“Edge 统一提供同源资源 URL”的方式是正确的，应该保留。

需要改变的是：

```text
单一固定 asset_root
```

变为：

```text
bundle_id → 对应已安装 wheel 的独立 asset_root
```

### 2.3 当前模型匹配依赖硬编码模糊字符串

当前 Material API 将节点的：

```text
type + class + config.type
```

拼成 identity，然后交给：

```python
model_registry.model_for_identity(identity)
```

现有模型 Registry 再用 `match_tokens` 做包含匹配。

例如：

```python
match_tokens=("robotic_arm", "arm_slider")
```

这种方式适合少量内置兼容模型，但不适合作为可扩展设备包合同，原因包括：

- 不同设备包可能出现同名 token；
- 包安装顺序可能影响冲突处理；
- 无法明确表达一个设备类使用哪个模型；
- 模型重命名时容易静默匹配到错误结果；
- 不适合为同一个设备声明 web、kinematics、collision 多种表示。

新方案应优先使用显式模型引用：

```yaml
bundle: szlab-poly-studio
model: szlab-poly-workcell
```

模糊 token 只保留为旧模型迁移兼容，不应成为新设备包的主要接口。

### 2.4 当前 ROS 可视化同样写死了 OS 模型根

下列代码也把模型目录固定在 `unilabos/device_mesh`：

- [`resource_visalization.py`](../../Uni-Lab-OS/unilabos/device_mesh/resource_visalization.py)
- [`resource_mesh_manager.py`](../../Uni-Lab-OS/unilabos/ros/nodes/presets/resource_mesh_manager.py)

因此只修改 HTTP Material API 还不够。

同一个模型 Registry 应当同时提供：

```text
resolve_public_url(...)  → 前端加载
resolve_local_path(...)  → ROS/XACRO/RViz/MoveIt 加载
```

不能让 Web 模型和 ROS 模型各自再扫描一次设备包，否则会形成两个模型事实源。

### 2.5 SZLab wheel 当前不会包含模型

SZLab 当前 `pyproject.toml` 的 package data 只包括：

- CSV；
- JSON；
- Profile YAML；
- Python 工作流。

对应文件：

- [`pyproject.toml`](../packages/szlab_poly_studio/pyproject.toml)

目前包内没有 `models/`，构建规则也没有包含 XACRO、URDF、STL、GLB、纹理和
模型配置文件。

所以要实现“安装设备包时模型也一起安装”，至少需要同时完成：

1. 在 Python package 内建立标准模型目录；
2. 将模型文件加入 wheel；
3. 在 distribution metadata 中声明模型发现入口；
4. 在 Edge 中增加安装包模型发现和安全解析；
5. 让节点或 Registry 条目显式引用 `bundle + model key`。

---

## 3. 推荐的设备包目录

### 3.1 SZLab distribution 推荐结构

```text
packages/szlab_poly_studio/
├── pyproject.toml
├── README.md
├── package.yaml
└── szlab_poly_studio/
    ├── __init__.py
    ├── model_bundle.py
    │
    ├── profile/
    │   ├── package.yaml
    │   └── device.yaml
    │
    ├── models/
    │   ├── manifest.yaml
    │   │
    │   ├── devices/
    │   │   ├── szlab_poly_studio/
    │   │   │   ├── macro_device.xacro
    │   │   │   ├── model.urdf
    │   │   │   ├── config/
    │   │   │   │   ├── joint_limits.yaml
    │   │   │   │   ├── initial_positions.yaml
    │   │   │   │   └── materials.xacro
    │   │   │   ├── meshes/
    │   │   │   │   ├── visual/
    │   │   │   │   │   ├── workcell.glb
    │   │   │   │   │   ├── base.stl
    │   │   │   │   │   └── robot_link_1.stl
    │   │   │   │   └── collision/
    │   │   │   │       ├── base.stl
    │   │   │   │       └── robot_link_1.stl
    │   │   │   └── textures/
    │   │   │       └── ...
    │   │   │
    │   │   ├── szlab_mixer_robot/
    │   │   │   ├── macro_device.xacro
    │   │   │   ├── config/
    │   │   │   ├── meshes/
    │   │   │   └── textures/
    │   │   │
    │   │   └── szlab_s08_cap_station/
    │   │       ├── macro_device.xacro
    │   │       ├── meshes/
    │   │       └── textures/
    │   │
    │   └── resources/
    │       ├── beaker_500ml/
    │       │   ├── model.glb
    │       │   └── collision.stl
    │       ├── sample_vial_250ml/
    │       │   ├── model.glb
    │       │   └── collision.stl
    │       ├── reagent_bottle_100ml/
    │       │   └── model.glb
    │       ├── powder_container/
    │       │   └── model.glb
    │       └── pipette_tip/
    │           └── model.glb
    │
    ├── workflows/
    ├── robot/
    ├── magnetic_stirring/
    ├── photoshotting/
    ├── pump/
    ├── decap_s08/
    ├── s07_solid_addition/
    └── s09_pipetting_station/
```

### 3.2 为什么模型必须放进 Python package 目录

应该放在：

```text
szlab_poly_studio/szlab_poly_studio/models/
```

而不是只放在：

```text
packages/szlab_poly_studio/models/
```

原因是前者可以被 setuptools 作为 package data 写入 wheel，并且安装后可以通过：

```python
importlib.resources.files("szlab_poly_studio")
```

定位。

仓库根目录或 distribution 根目录的普通文件，如果没有额外 data-files 配置，
安装后的位置和可发现性都不如 package data 稳定。

### 3.3 `devices/` 和 `resources/` 目录名应保留

现有前端会根据模型 URL 中是否包含：

```text
/devices/
```

或：

```text
/resources/
```

判断如何加载模型，并据此计算 `mesh_path`。

对应代码：

- [`modelRuntime.ts`](../../uni-lab-fe/packages/pascal-lab-plugin/src/modelRuntime.ts)

当前逻辑大致是：

```typescript
const meshPath = modelPath.includes('/devices/')
  ? modelPath.split('/devices/')[0]
  : modelPath.split('/resources/')[0]
```

因此新包的 HTTP URL 最好继续保持：

```text
.../assets/devices/{model_key}/macro_device.xacro
```

和：

```text
.../assets/resources/{model_key}/model.glb
```

这样现有前端不需要重新定义资源根算法。

### 3.4 XACRO 目录名和宏名必须一致

当前前端会从入口文件的父目录推导宏名。

例如入口：

```text
devices/szlab_poly_studio/macro_device.xacro
```

前端会调用：

```xml
<xacro:szlab_poly_studio ... />
```

所以入口文件内部应声明：

```xml
<xacro:macro
  name="szlab_poly_studio"
  params="mesh_path:='' parent_link:='' station_name:='' device_name:=''">
  ...
</xacro:macro>
```

如果目录名是 `szlab_poly_studio`，宏名却是 `workcell`，当前前端会加载失败。

这个约束应当加入模型包构建测试。

### 3.5 视觉网格和碰撞网格应分开

建议：

```text
meshes/visual/
meshes/collision/
```

视觉网格可以：

- 面数较高；
- 带材质和纹理；
- 使用 GLB；
- 保留更真实的外观。

碰撞网格应：

- 尽量低面数；
- 使用封闭几何；
- 避免大量小零件；
- 优先保证规划速度和稳定性。

不要直接把高精度 CAD 导出的全部三角面同时用于 visual 和 collision。

---

## 4. 模型清单 `manifest.yaml`

### 4.1 模型清单的职责

`manifest.yaml` 是设备包与 Edge 之间的模型接口。

它应描述：

- 模型包稳定 ID；
- 模型包 schema 版本；
- 包含哪些模型；
- 每个模型适用于哪些设备或资源 identity；
- 各个模型表示的用途；
- 模型入口相对路径；
- 格式；
- 单位和坐标轴；
- 默认变换；
- XACRO 宏名；
- 可选实例模型和安装点；
- 模型资源兼容要求。

它不应包含：

- 宿主机绝对路径；
- `site-packages` 路径；
- `file:///home/...`；
- Edge 的 IP 或端口；
- OSS 临时 URL；
- 用户凭证。

### 4.2 推荐清单示例

```yaml
schema_version: 1

bundle:
  id: szlab-poly-studio
  display_name: SZLab 聚合物工作站模型包
  source_namespace: szlab

models:
  - key: szlab-poly-workcell
    display_name: SZLab 聚合物工作站整机

    applies_to:
      - kind: resource
        class: szlab_poly_studio_deck

    representations:
      web:
        format: gltf
        entry: devices/szlab_poly_studio/meshes/visual/workcell.glb

      kinematics:
        format: xacro
        entry: devices/szlab_poly_studio/macro_device.xacro
        macro: szlab_poly_studio

      collision:
        format: xacro
        entry: devices/szlab_poly_studio/macro_device.xacro
        macro: szlab_poly_studio

    coordinates:
      units: meter
      up_axis: z

    transform:
      position: [0.0, 0.0, 0.0]
      rotation_rpy: [0.0, 0.0, 0.0]
      scale: [1.0, 1.0, 1.0]

  - key: szlab-mixer-robot
    display_name: SZLab 搬运机械臂

    applies_to:
      - kind: device
        class: szlab_mixer_robot

    representations:
      web:
        format: xacro
        entry: devices/szlab_mixer_robot/macro_device.xacro
        macro: szlab_mixer_robot

      kinematics:
        format: xacro
        entry: devices/szlab_mixer_robot/macro_device.xacro
        macro: szlab_mixer_robot

    coordinates:
      units: meter
      up_axis: z

    transform:
      position: [0.0, 0.0, 0.0]
      rotation_rpy: [0.0, 0.0, 0.0]
      scale: [1.0, 1.0, 1.0]

  - key: szlab-beaker-500ml
    display_name: SZLab 500 mL 烧杯

    applies_to:
      - kind: resource
        class: szlab_beaker_500ml

    representations:
      web:
        format: gltf
        entry: resources/beaker_500ml/model.glb

      collision:
        format: stl
        entry: resources/beaker_500ml/collision.stl

    coordinates:
      units: meter
      up_axis: y

    transform:
      position: [0.0, 0.0, 0.0]
      rotation_rpy: [0.0, 0.0, 0.0]
      scale: [1.0, 1.0, 1.0]
```

### 4.3 为什么应支持多个 representation

同一个设备对不同消费者的最佳文件可能不同。

```text
前端 Web 3D
  → 更关心加载速度、材质、纹理和渲染面数

ROS/RViz
  → 更关心 link、joint、TF 和 robot_description

MoveIt
  → 更关心碰撞几何、关节限制和规划性能
```

如果清单只提供一个 `path`，所有消费者都被迫使用同一种表示，后续很容易出现：

- 浏览器被迫下载大量 STL；
- MoveIt 被迫使用高面数视觉网格；
- 静态设备也被迫走 XACRO；
- 视觉优化会影响运动学模型；
- 运动学修改会无意改变前端资源入口。

因此推荐由 Edge 根据 consumer 选择表示：

```text
consumer=web         → representations.web
consumer=rviz        → representations.kinematics
consumer=moveit      → representations.collision / kinematics
```

第一版如果暂时不想支持多个表示，可以只声明：

```yaml
representations:
  web:
    format: xacro
    entry: devices/szlab_poly_studio/macro_device.xacro
    macro: szlab_poly_studio
```

后续再增加 GLB，不需要改变模型 identity。

### 4.4 identity 匹配优先级

推荐 Edge 按以下顺序选择模型：

1. 图节点显式指定 `bundle + model key`；
2. Registry 中 `@device` / `@resource` 的显式模型引用；
3. 模型清单 `applies_to` 对 class 的精确匹配；
4. 旧系统 `match_tokens` 兼容匹配；
5. 没有匹配时返回 `format=none`。

不要使用安装顺序决定冲突结果。

如果两个模型包声明相同的精确 identity，Edge 应启动失败或将冲突模型标记为
不可用，并给出清晰诊断，不能静默选择其中一个。

---

## 5. wheel 如何声明模型包

### 5.1 package data

SZLab distribution 的 `pyproject.toml` 需要增加模型文件。

示例：

```toml
[tool.setuptools.package-data]
szlab_poly_studio = [
  "*.csv",
  "*.json",
  "profile/*.yaml",
  "workflows/*.py",
  "magnetic_stirring/*.csv",
  "photoshotting/*.csv",
  "pump/*.csv",
  "decap_s08/*.csv",
  "s07_solid_addition/*.csv",
  "s07_solid_addition/*.json",
  "s09_pipetting_station/*.csv",

  "models/**/*.yaml",
  "models/**/*.yml",
  "models/**/*.xacro",
  "models/**/*.urdf",
  "models/**/*.srdf",
  "models/**/*.stl",
  "models/**/*.dae",
  "models/**/*.obj",
  "models/**/*.mtl",
  "models/**/*.gltf",
  "models/**/*.glb",
  "models/**/*.png",
  "models/**/*.jpg",
  "models/**/*.jpeg",
]
```

构建后不能只检查源目录，必须检查 wheel 本身：

```bash
unzip -l dist/szlab/unilabos_szlab_poly_studio-*.whl
```

至少应看到：

```text
szlab_poly_studio/models/manifest.yaml
szlab_poly_studio/models/devices/.../macro_device.xacro
szlab_poly_studio/models/devices/.../meshes/...
```

### 5.2 安装发现 entry point

建议增加独立的 Python entry point group：

```toml
[project.entry-points."unilabos.model_bundles"]
szlab-poly-studio = "szlab_poly_studio.model_bundle:get_model_bundle"
```

`model_bundle.py` 可以保持非常小：

```python
def get_model_bundle() -> dict[str, str]:
    return {
        "package": "szlab_poly_studio",
        "manifest": "models/manifest.yaml",
    }
```

这里的 entry point 只负责告诉 Edge：

```text
这个已安装 distribution 提供一个模型 bundle；
bundle 清单位于哪个 Python package 的哪个相对位置。
```

它不负责：

- 启动硬件；
- 创建 OPC UA 连接；
- 导入所有设备驱动；
- 运行 XACRO；
- 启动 ROS 节点；
- 返回宿主机绝对路径。

这样 Edge 可以只读取安装元数据和模型清单，不会因为发现模型而连接真实设备。

### 5.3 为什么不建议扫描整个 `site-packages`

不建议由 Edge：

```text
遍历 site-packages
→ 搜索所有名为 models 或 device_mesh 的目录
```

因为：

- 扫描成本不可控；
- 很容易把普通第三方库的 `models/` 误识别为设备模型；
- 没有稳定的 bundle identity；
- 无法处理重复和版本；
- 无法知道哪个 manifest 可信；
- 测试和卸载行为不明确。

entry point 是显式安装合同，发现范围更小，错误也更容易诊断。

---

## 6. `mesh_path` 应该如何使用

### 6.1 `mesh_path` 的正确语义

虽然字段名叫 `mesh_path`，它实际上不应只表示 mesh 文件目录。

在现有模型中，它还被用于：

- `xacro:include`；
- `xacro.load_yaml`；
- STL；
- joint limit；
- controller 配置；
- SRDF；
- 其他子 XACRO。

因此更准确的语义是：

```text
模型 bundle 的 asset root
```

为兼容现有模型和前端，可以继续保留参数名 `mesh_path`，但在新合同中将它定义为：

> 当前模型包资源根；其下必须包含 `devices/` 或 `resources/`。

### 6.2 浏览器端的 `mesh_path`

假设 Edge 返回模型入口：

```text
/api/v1/model-bundles/szlab-poly-studio/abc123/assets/devices/szlab_poly_studio/macro_device.xacro
```

前端按 `/devices/` 切分后得到：

```text
/api/v1/model-bundles/szlab-poly-studio/abc123/assets
```

然后向 XACRO 宏传入：

```xml
mesh_path="/api/v1/model-bundles/szlab-poly-studio/abc123/assets"
```

XACRO 中：

```xml
<mesh
  filename="file://${mesh_path}/devices/szlab_poly_studio/meshes/visual/base.stl" />
```

展开后经过现有前端的 `file://` 修正逻辑，最终请求：

```text
/api/v1/model-bundles/szlab-poly-studio/abc123/assets/devices/szlab_poly_studio/meshes/visual/base.stl
```

因此 `mesh_path` 与新模型包 URL 结构天然兼容。

### 6.3 ROS/RViz/MoveIt 端的 `mesh_path`

同一个 XACRO 在 Edge 本机使用时，Edge 的模型 Registry 返回包内本地根：

```text
/path/to/python/site-packages/szlab_poly_studio/models
```

Edge 调用 XACRO 时传入：

```text
mesh_path=/path/to/python/site-packages/szlab_poly_studio/models
```

XACRO 最终解析：

```text
/path/to/python/site-packages/szlab_poly_studio/models/devices/...
```

所以同一份 XACRO 可以同时支持：

```text
Web：mesh_path = HTTP asset root
ROS：mesh_path = local package asset root
```

这正是保留 `mesh_path` 的最大价值。

### 6.4 不要在 XACRO 中写绝对路径

禁止：

```xml
<mesh filename="file:///home/changjunhan/.../base.stl" />
```

禁止：

```xml
<xacro:include filename="/opt/unilab/.../robot.xacro" />
```

禁止：

```xml
<mesh filename="https://temporary-oss-url/.../base.stl" />
```

应该统一写为：

```xml
<mesh
  filename="file://${mesh_path}/devices/szlab_poly_studio/meshes/visual/base.stl" />
```

和：

```xml
<xacro:include
  filename="${mesh_path}/devices/szlab_poly_studio/config/materials.xacro" />
```

### 6.5 `xacro.load_yaml` 的当前前端限制

当前前端会预加载形如下面的 YAML：

```xml
${xacro.load_yaml(mesh_path + '/devices/.../joint_limits.yaml')}
```

它使用正则从入口 XACRO 中识别：

```text
xacro.load_yaml(mesh_path + '固定字符串')
```

因此第一阶段建议：

- `load_yaml` 使用静态相对后缀；
- 不在路径中拼接复杂表达式；
- 关键 `load_yaml` 尽量直接出现在入口 XACRO；
- 不依赖 ROS `$(find package_name)`；
- 不使用只在 Python XACRO 中支持、浏览器 parser 不支持的扩展。

例如建议：

```xml
<xacro:property
  name="joint_limits"
  value="${xacro.load_yaml(
    mesh_path + '/devices/szlab_poly_studio/config/joint_limits.yaml'
  )}" />
```

不建议：

```xml
${xacro.load_yaml(
  mesh_path + '/devices/' + device_type + '/config/' + config_name
)}
```

长期更稳妥的做法是：

- 构建阶段把权威 XACRO 编译并校验成 URDF；
- 或增强前端递归解析 XACRO include 和 YAML 依赖；
- 或为 Web 声明独立 GLB 表示。

---

## 7. Edge 模型 Registry 的推荐设计

### 7.1 统一模块

建议将当前只处理内置模型的：

```text
MaterialModelRegistry
```

演进为统一的：

```text
ModelBundleRegistry
```

对调用者只暴露少量接口：

```python
list_bundles()
model_for_node(node, consumer="web")
resolve_public_url(model_ref)
resolve_local_asset(model_ref)
resolve_bundle_asset(bundle_id, revision, relative_path)
```

模块内部负责：

- 内置 OS 模型；
- 已安装 wheel 模型；
- entry point 发现；
- manifest 校验；
- identity 映射；
- 版本和 content hash；
- URL 生成；
- 本地路径解析；
- 目录穿越检查；
- 重复 identity 检查；
- MIME 和缓存元数据。

Material API、ROS 可视化和 MoveIt 都应通过这个统一模块读取模型。

### 7.2 内置模型也应被视为一个 bundle

当前 `unilabos/device_mesh` 可以注册成：

```text
bundle_id = unilabos-core-models
```

这样 Edge 内部只有一套行为：

```text
内置 bundle adapter
安装包 bundle adapter
             │
             ▼
      ModelBundleRegistry
```

而不是：

```text
如果是内置模型走 material_models.py
如果是外部模型走另一套逻辑
如果是 ROS 再走第三套逻辑
```

### 7.3 Edge 启动发现流程

建议启动顺序：

```text
1. 读取内置模型 bundle
2. 读取 importlib.metadata entry_points
3. 选择 group = unilabos.model_bundles
4. 加载每个极小的 bundle provider
5. 使用 importlib.resources 定位 manifest
6. 校验 manifest schema
7. 校验模型入口和依赖资源
8. 计算 bundle content hash / revision
9. 建立 identity → model key 索引
10. 检测重复 bundle、重复 model key、重复 identity
11. 发布模型 HTTP 路由
12. Material API 和 ROS 运行时开始消费 Registry
```

如果设备包在 Edge 启动后才安装，第一版可以要求重启 Edge。

不要在第一版实现“运行中 pip install 后自动热加载模型”，因为热加载还涉及：

- Registry 原子替换；
- 浏览器缓存；
- ROS robot_description；
- 已加载场景对象；
- 设备包卸载；
- 正在运行的工作流。

### 7.4 错误处理

推荐错误策略：

| 错误 | 行为 |
| --- | --- |
| bundle manifest 无法读取 | bundle 不可用，启动诊断明确报告 |
| manifest schema 错误 | bundle 不可用 |
| 模型入口不存在 | 对应 bundle 不可用 |
| 路径越出 bundle root | 拒绝整个引用 |
| bundle ID 重复 | 启动失败或两个 bundle 都禁用，不能静默覆盖 |
| model key 重复 | bundle 校验失败 |
| identity 重复 | 模型匹配失败并报告冲突 |
| 某节点没有模型 | 正常返回 `format=none`，不影响设备执行 |
| 模型资源 HTTP 404 | 记录模型合同错误，不影响硬件动作执行 |

设备执行和 3D 可视化应解耦：

```text
模型坏了
≠
设备驱动不能运行
```

但用于 MoveIt 的 collision/kinematics 模型缺失时，依赖 MoveIt 的动作必须明确
不可用，不能退化为无碰撞规划。

---

## 8. Edge 对外模型接口

### 8.1 推荐 URL

建议增加通用模型接口：

```text
GET /api/v1/model-bundles
GET /api/v1/model-bundles/{bundle_id}
GET /api/v1/model-bundles/{bundle_id}/{revision}/assets/{asset_path}
```

示例：

```text
GET /api/v1/model-bundles/szlab-poly-studio/abc123/assets/devices/szlab_poly_studio/macro_device.xacro
```

其中：

- `bundle_id` 防止不同设备包的相对路径冲突；
- `revision` 用于缓存隔离；
- `assets` 后仍保留 `devices/` 或 `resources/`；
- `asset_path` 只表示包内模型相对路径；
- URL 中不出现 Python distribution 的物理安装路径。

### 8.2 Material API 返回的模型信息

Material Aggregate 中可以继续返回前端已经消费的结构：

```json
{
  "rendering": {
    "kind": "robotic-arm",
    "dimensionsMm": [1200, 1800, 1200],
    "scale": [1, 1, 1],
    "model": {
      "bundle": "szlab-poly-studio",
      "key": "szlab-mixer-robot",
      "path": "/api/v1/model-bundles/szlab-poly-studio/abc123/assets/devices/szlab_mixer_robot/macro_device.xacro",
      "format": "xacro",
      "position": [0, 0, 0],
      "rotation": [0, 0, 0],
      "attachPoints": []
    }
  }
}
```

前端不需要知道：

- 模型来自哪个 `site-packages`；
- provider Python 模块；
- wheel 在磁盘上的位置；
- Edge 本地用户名；
- 模型的本地绝对路径。

### 8.3 旧接口兼容

当前前端和测试正在使用：

```text
/api/v1/material-models
/api/v1/material-models/assets/...
```

迁移可以分两步：

1. `ModelBundleRegistry` 先接管旧接口的实现；
2. 增加新 `/api/v1/model-bundles` 接口；
3. Material API 开始返回新 URL；
4. 旧 URL 保留一个版本周期作为 adapter；
5. 前端和测试全部迁移后再决定是否删除。

---

## 9. 设备和资源如何引用模型

### 9.1 推荐的 Registry 模型引用

Uni-Lab-OS 的 `@device` 和 `@resource` 已经支持 `model` 字典。

SZLab 设备可以声明：

```python
@device(
    id="szlab_mixer_robot",
    display_name="SZLab 搬运机械臂",
    category=["custom", "robotic_arm"],
    model={
        "bundle": "szlab-poly-studio",
        "key": "szlab-mixer-robot",
    },
)
class SZLabRobot:
    ...
```

物料可以声明：

```python
@resource(
    id="szlab_beaker_500ml",
    displayname="SZLab 500 mL 烧杯",
    category=["szlab_poly_studio", "container", "beaker"],
    model={
        "bundle": "szlab-poly-studio",
        "key": "szlab-beaker-500ml",
    },
)
def beaker_500ml(...):
    ...
```

新的 `model` 字典只存稳定引用，不存：

```text
path=/home/...
path=site-packages/...
path=https://...
```

### 9.2 图节点显式覆盖

如果同一设备类的某个实例确实要使用不同模型，可在图节点中覆盖：

```json
{
  "id": "szlab_mixer_robot_2",
  "type": "device",
  "class": "szlab_mixer_robot",
  "model": {
    "bundle": "szlab-poly-studio",
    "key": "szlab-mixer-robot-long-rail"
  }
}
```

这应是实例级例外，不应要求每个图节点重复写默认模型。

### 9.3 模型包与设备包版本一致

模型不单独从随机 URL 更新。

推荐：

```text
unilabos-szlab-poly-studio 0.2.0
├── 驱动 0.2.0
├── Profile 0.2.0
└── 模型资源 0.2.0
```

这样：

- 升级 wheel 同时升级模型；
- 回滚 wheel 同时回滚模型；
- 模型与动作、关节、站位保持一致；
- bug 报告可以直接引用 distribution 版本；
- Edge 可用 wheel 版本和文件 hash 生成模型 revision。

---

## 10. XACRO、URDF、GLB 应如何选择

### 10.1 XACRO 不是 mesh 格式

XACRO 是生成 URDF/XML 的宏系统。

它主要表达：

- link；
- joint；
- visual；
- collision；
- inertial；
- 参数；
- include；
- 重复结构；
- 不同设备型号的配置差异。

实际几何通常仍然来自：

- STL；
- DAE；
- OBJ；
- 其他 URDF loader 支持的 mesh。

所以“使用 XACRO”通常意味着：

```text
XACRO 负责结构
mesh 文件负责几何
YAML 负责参数
```

### 10.2 什么时候继续使用 XACRO

满足以下任一条件时，建议保留 XACRO：

- 模型有关节；
- 需要接入 ROS robot_state_publisher；
- 需要 RViz；
- 需要 MoveIt；
- 需要 collision；
- 需要末端执行器或安装 link；
- 一个模型需要支持多个配置；
- 需要用宏减少重复 link；
- 需要从 YAML 读取关节限制和初始位置。

SZLab 搬运机械臂显然属于这一类。

### 10.3 什么时候 GLB 更好

满足以下条件时，GLB 更适合作为 Web 表示：

- 设备完全静态；
- 只需要浏览器展示；
- 需要 PBR 材质和纹理；
- 希望模型为单文件；
- 希望减少大量 STL HTTP 请求；
- 不需要 ROS link/joint；
- 模型由 DCC/CAD 流程直接生成。

例如：

- 静态机柜；
- 工作站外壳；
- 泵站外观；
- 烧杯；
- 样品瓶；
- 试剂瓶；
- 粉罐。

### 10.4 推荐的 SZLab 选择

| SZLab 对象 | Web | ROS/运动学 | Collision |
| --- | --- | --- | --- |
| 整个工作站静态外观 | GLB | 可选 XACRO | 简化 STL/primitive |
| 搬运机械臂 | XACRO 或分 link GLB | XACRO/URDF | 低面数 STL |
| S04～S09 静态工位 | GLB | 通常不需要 | 简化 STL/primitive |
| 有可动门、盖、夹具的工位 | XACRO | XACRO/URDF | 低面数 STL |
| 烧杯、样品瓶、粉罐 | GLB | 不需要 | primitive 或低面数 STL |
| 枪头大量实例 | 小 GLB/InstancedMesh | 不需要 | 通常不逐个做 collision |

### 10.5 第一版建议

如果当前已有完整 XACRO：

1. 不要为了“更现代”立即重做全部模型；
2. 先把现有 XACRO、STL、YAML 原样迁进 wheel；
3. 使用模型 bundle 和 `mesh_path` 打通安装、发现和读取；
4. 增加 clean-wheel E2E；
5. 再按加载性能逐步增加 GLB web representation。

如果当前只有一整套静态 CAD 模型，没有任何关节需求：

1. 优先导出一个优化后的 GLB；
2. 不需要为了形式统一强行套 XACRO；
3. 如 MoveIt 需要碰撞，再单独提供 collision 描述。

---

## 11. SZLab 模型粒度

当前 `szlab-local-debug.json` 中多个设备和资源的位姿都是零，设备节点之间也没有
形成完整的 3D 父子装配关系。

因此需要先决定模型粒度。

### 11.1 方案 A：整机组合模型

```text
一个 szlab_poly_studio XACRO/GLB
└── 内部包含 S01～S11、机械臂、台面和固定设备
```

优点：

- 最快获得完整、位置正确的 3D 场景；
- 不依赖当前图中每个节点的准确 pose；
- 设备包只需一个主要入口。

缺点：

- 单个工位难以独立选中和替换；
- 图节点与模型 link 的映射要额外声明；
- 可能与后续单设备模型重复渲染；
- 单个工位升级也要更新整机模型。

适合第一阶段展示和整机数字孪生底模。

### 11.2 方案 B：每个设备独立模型

```text
szlab_poly_studio_deck
├── s1_workstation
├── szlab_mixer_robot
├── szlab_mixer_stirrer
├── szlab_mixer_photoshotting
├── szlab_mixer_pump
├── szlab_s07_solid_addition
├── szlab_s08_cap_station
└── szlab_mixer_pipetting_station
```

优点：

- 与设备 Registry 和图节点一一对应；
- 每个设备可以独立选中、隐藏和更新；
- 更适合状态联动和可动部件；
- 设备可复用到其他工作站。

缺点：

- 必须先校准所有节点的 parent 和 pose；
- 坐标原点标准必须一致；
- 容易因为重复建模产生穿模；
- 初期工作量更大。

### 11.3 推荐做法

推荐两阶段：

```text
阶段 1
  整机 GLB 或组合 XACRO作为工作站底模
  机械臂单独使用 XACRO
  物料单独使用 GLB

阶段 2
  校准设备图中的 parent/pose
  将 S04～S09 拆成独立模型
  从整机底模中删除已经独立渲染的设备几何
```

必须避免：

```text
组合模型中已经有机械臂
+
机械臂节点又加载一遍模型
=
场景中出现两个重叠机械臂
```

---

## 12. 安全和资源读取规则

### 12.1 路径限制

模型 manifest 中的路径必须：

- 是 POSIX 风格相对路径；
- 位于 bundle `models/` 根下；
- 经过 `resolve()` 后仍在 bundle 根下；
- 不包含 `..` 越界；
- 不接受绝对路径；
- 不跟随越出 bundle 根的符号链接。

必须拒绝：

```text
../../secrets.env
/etc/passwd
C:\Users\...
file:///home/...
```

### 12.2 文件类型

第一版建议允许：

```text
.xacro
.urdf
.srdf
.yaml
.yml
.stl
.dae
.obj
.mtl
.gltf
.glb
.png
.jpg
.jpeg
```

不应通过模型资源接口提供：

```text
.py
.so
.dll
.exe
.env
日志
数据库
凭证文件
```

### 12.3 HTTP 缓存

URL 中包含 content revision 时，可以返回：

```text
Cache-Control: public, max-age=31536000, immutable
ETag: "<asset-sha256>"
```

manifest 或 bundle 列表可以使用较短缓存，并支持 ETag。

模型文件变化后 revision 必须变化，防止浏览器继续使用旧 STL 或旧 XACRO。

---

## 13. 推荐的完整读取链路

### 13.1 安装

```bash
pip install unilabos-szlab-poly-studio-0.2.0-py3-none-any.whl
```

安装结果：

```text
site-packages/
├── szlab_poly_studio/
│   ├── Python 驱动
│   ├── profile/
│   └── models/
└── unilabos_szlab_poly_studio-0.2.0.dist-info/
    └── entry_points.txt
```

### 13.2 Edge 启动

```text
importlib.metadata.entry_points()
  → group=unilabos.model_bundles
  → szlab-poly-studio provider
  → models/manifest.yaml
  → 校验
  → 建立索引
```

### 13.3 节点匹配

```text
graph node
  class = szlab_mixer_robot
       │
       ▼
Registry model ref
  bundle = szlab-poly-studio
  key = szlab-mixer-robot
       │
       ▼
ModelBundleRegistry
```

### 13.4 Web 模型

```text
Material API
  → representations.web
  → 生成 Edge 同源 URL
  → 前端 fetch
  → XACRO/URDF/GLB loader
  → Three.js/Pascal 场景
```

如果是 XACRO：

```text
入口 URL
  → 从 /devices/ 之前截出 mesh_path
  → 加载 include/YAML/STL
  → 展开 URDF
  → Three.js 加载各 link mesh
```

### 13.5 ROS 模型

```text
ROS/RViz/MoveIt
  → representations.kinematics
  → ModelBundleRegistry.resolve_local_asset()
  → 本地 XACRO 路径
  → mesh_path=包内 models 根
  → robot_description / collision scene
```

---

## 14. 迁移实施步骤

### 阶段 1：把模型真正装进 wheel

1. 创建 `szlab_poly_studio/models/`；
2. 按 `devices/` 和 `resources/` 整理资产；
3. 清除所有宿主机绝对路径；
4. 让 XACRO 统一从 `mesh_path` 引用依赖；
5. 增加 `models/manifest.yaml`；
6. 更新 package data；
7. 构建 wheel 并检查 wheel 文件列表。

验收：

```text
只拿 wheel，不拿源码仓库，也能看到完整模型资源。
```

### 阶段 2：Edge 发现模型 bundle

1. 增加 `unilabos.model_bundles` entry point；
2. 增加 `ModelBundleRegistry`；
3. 将内置模型转换为内置 bundle；
4. 启动时发现外部 bundle；
5. 增加 schema 和路径校验；
6. 增加冲突诊断；
7. 保留旧 `MaterialModelRegistry` 接口作为临时 adapter。

验收：

```text
安装 wheel + 启动 Edge
→ GET bundles 能看到 szlab-poly-studio
```

### 阶段 3：Edge 提供模型资源

1. 增加 bundle-aware asset URL；
2. 根据 bundle 和 revision 解析资源；
3. 拒绝目录穿越；
4. 配置 MIME、ETag、Cache-Control；
5. 让旧接口转发到新 Registry；
6. 确保 Electron `Origin: null` 访问策略仍然正确。

验收：

```text
XACRO、YAML、GLB、STL 全部由当前 Edge 返回 200。
```

### 阶段 4：设备 identity 绑定模型

1. 给 SZLab `@device` 增加稳定模型引用；
2. 给 SZLab `@resource` 增加稳定模型引用；
3. Material API 优先读取显式模型引用；
4. `applies_to` 作为精确 class 兜底；
5. 旧 `match_tokens` 降为兼容逻辑。

验收：

```text
节点 class 不变时，模型选择不受安装顺序和模糊 token 影响。
```

### 阶段 5：统一 Web 和 ROS 解析

1. `resource_visalization.py` 不再自己拼 OS 固定目录；
2. `resource_mesh_manager.py` 不再自己拼 OS 固定目录；
3. 两者都依赖 `ModelBundleRegistry.resolve_local_asset()`；
4. Web 使用同一 Registry 的 `resolve_public_url()`；
5. 添加 XACRO 本地根和 HTTP 根双模式测试。

验收：

```text
同一个 model key：
Web 能加载；
RViz 能加载；
MoveIt 能加载对应 collision；
三者来自同一个 wheel 版本。
```

---

## 15. 必须增加的测试

### 15.1 wheel 内容测试

- wheel 包含 manifest；
- wheel 包含所有模型入口；
- wheel 包含所有 XACRO include；
- wheel 包含所有 `load_yaml` 文件；
- wheel 包含所有 visual/collision mesh；
- wheel 不包含本地日志、SQLite、缓存和凭证。

### 15.2 clean-install 测试

在没有 SZLab 源码目录参与的环境中：

1. 只安装 wheel；
2. 运行 entry point discovery；
3. 读取 manifest；
4. 定位模型入口；
5. 解析所有资源。

这是验证“模型真的跟着设备包走”的关键测试。

editable install 通过并不能证明 wheel 正确。

### 15.3 Registry 测试

- bundle ID 唯一；
- model key 唯一；
- identity 冲突被拒绝；
- manifest schema 错误被拒绝；
- 缺少入口文件被拒绝；
- `../` 路径被拒绝；
- 绝对路径被拒绝；
- 符号链接越界被拒绝；
- 没有模型的节点安全返回 none。

### 15.4 HTTP 测试

- XACRO 返回 200；
- YAML 返回 200；
- GLB 返回 200；
- STL 返回 200；
- 不存在资源返回 404；
- 目录穿越返回 400/404；
- URL 不暴露本地路径；
- revision 变化会改变 URL 或 ETag；
- Electron `Origin: null` 可以按既定策略读取。

### 15.5 XACRO 测试

- 入口目录名与宏名一致；
- `mesh_path` 使用本地目录时可展开；
- `mesh_path` 使用 HTTP root 时可被前端加载；
- 所有 include 存在；
- 所有 YAML 存在；
- 所有 mesh 存在；
- URDF link 名唯一；
- joint parent/child 合法；
- collision 网格可以加载；
- 不包含 `$(find ...)` 等仅 ROS package 环境可解析的路径。

### 15.6 浏览器 E2E

- 打开 SZLab 3D 场景；
- 没有 request failure；
- 没有 browser console error；
- 工作站模型只出现一次；
- 机械臂 link 正确；
- 模型比例正确；
- Z-up 到 Three.js Y-up 转换正确；
- 材料节点位置与模型安装点一致；
- 页面刷新后缓存模型仍与当前 revision 一致。

---

## 16. 对 SZLab 当前仓库的具体建议

### 16.1 先增加这三个文件/目录

```text
packages/szlab_poly_studio/szlab_poly_studio/
├── model_bundle.py
└── models/
    ├── manifest.yaml
    ├── devices/
    └── resources/
```

### 16.2 第一批模型

建议第一批只覆盖：

1. `szlab_poly_studio` 整机静态模型；
2. `szlab_mixer_robot` 机械臂 XACRO；
3. `szlab_beaker_500ml`；
4. `szlab_sample_vial_250ml`；
5. `szlab_liquid_reagent_bottle_100ml`；
6. `szlab_powder_container`。

这样能够先验证：

- 设备模型；
- 可动模型；
- 物料模型；
- XACRO；
- GLB；
- collision；
- wheel 安装发现；
- Edge HTTP 读取。

不要一开始就同时迁移所有 S01～S11 的全部 CAD 细节。

### 16.3 当前图位姿需要补充

当前 SZLab debug graph 中的设备和资源 pose 基本都是零。

如果采用独立设备模型，必须进一步补充：

- 每个工位相对工作站根的 parent；
- XYZ；
- RPY；
- 单位；
- 机械臂基座坐标；
- 各 station 的安装原点；
- 物料 Site；
- 末端执行器 attach link。

否则模型已经能从设备包读取，但会全部叠在世界原点。

### 16.4 近期最小可落地方案

如果目标是尽快验证整个链路，推荐：

```text
1. 将整机模型放入 wheel
2. 保留 XACRO + mesh_path
3. 增加模型 manifest 和 entry point
4. Edge 增加 bundle discovery
5. Edge 通过带 bundle_id 的 URL 提供资源
6. 将整机模型绑定到 SZLab 工作站根/Deck
7. 前端继续使用现有 XACRO loader
8. clean-wheel E2E 验证
```

等这条链路稳定后，再为静态部分增加 GLB，并逐步拆分各工位。

---

## 17. 最终推荐合同

设备包需要保证：

```text
我是谁
  → distribution / profile / bundle id

我有哪些设备和资源
  → @device / @resource / device spec

它们使用哪些模型
  → bundle + model key

模型入口在哪里
  → models/manifest.yaml 中的相对路径

模型依赖在哪里
  → models/devices 和 models/resources

怎样被 Edge 发现
  → unilabos.model_bundles entry point
```

Edge 需要保证：

```text
发现安装包
→ 校验模型清单
→ 建立稳定 identity 索引
→ 为 Web 生成同源 URL
→ 为 ROS 生成本地路径
→ 将正确的 asset root 注入 mesh_path
→ 不暴露宿主机路径
→ 不允许目录穿越
```

前端需要保证：

```text
读取 Material API 中的 model.path / format
→ 对 XACRO 从 /devices/ 或 /resources/ 推导 mesh_path
→ 从同一 Edge 获取 XACRO、YAML 和 mesh
→ 对 GLB 直接加载入口文件
```

最终效果是：

```text
安装设备 wheel
        │
        ├── 设备驱动可发现
        ├── Profile 可发现
        ├── 工作流可发现
        └── 3D 模型可发现
                │
                ├── Web 3D
                ├── RViz
                └── MoveIt
```

模型从此属于设备包版本，而不是 Uni-Lab-OS 主仓库中的一份外部副本。
