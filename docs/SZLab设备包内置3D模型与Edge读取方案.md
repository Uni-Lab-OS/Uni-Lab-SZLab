# SZLab 设备包内置 3D 模型与 Edge 读取方案

## 结论

SZLab 模型应直接放在对应驱动目录的 `models/` 下，并由该驱动的 `@device(model=...)` 声明。
资源模型采用相同原则，放在 `resources/<resource_id>/models/` 并由 `@resource` 声明。仓库中
不再存在包级模型 provider 或总清单。

## 当前已落地结构

```text
szlab_poly_studio/
├── devices/
│   ├── szlab_mixer_robot/
│   │   ├── device.py
│   │   ├── robot_S01.py ... robot_S11.py
│   │   └── models/shape.yml
│   ├── szlab_mixer_pump/
│   │   ├── device.py
│   │   ├── sensors.py
│   │   ├── pump_nodes.csv
│   │   └── models/shape.yml
│   ├── szlab_mixer_stirrer/models/shape.yml
│   ├── szlab_mixer_photoshotting/models/shape.yml
│   └── szlab_s07_solid_addition/models/shape.yml
└── resources/
    ├── materials.py
    ├── warehouses.py
    └── <resource_id>/models/shape.yml
```

原全局 2.5D 外形数据已经无损拆到上述归属目录。每个资产由相应装饰器直接引用。仓库当前
没有提交真实 Xacro/mesh/GLB，所以不能声称 3D 闭环已完成；现在完成的是目录、绑定和打包
合同，以及已有 2.5D 资产的迁移。文件使用 `.yml` 是为了避开当前 OS 将设备子树内
`*.yaml` 误当旧式注册表的兼容缺陷；内容仍是标准 YAML，实际定位以装饰器 `entry` 为准。

## 机械臂加入真实 3D 模型后的目录

```text
szlab_poly_studio/devices/szlab_mixer_robot/
├── device.py
└── models/
    ├── device.xacro
    ├── meshes/
    │   ├── rail.stl
    │   ├── base.stl
    │   └── arm.dae
    ├── textures/
    ├── config/
    └── shape.yml
```

`device.py` 中的目标声明：

```python
@device(
    id="szlab_mixer_robot",
    display_name="SZLab Mixer 机器人任务",
    category=["robotic_arm"],
    model={
        "format": "xacro",
        "entry": "models/device.xacro",
        "macro": "szlab_mixer_robot",
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "models/shape.yml",
        },
    },
)
class SzlabMixerRobotDevice:
    ...
```

一个 Xacro 就是默认的完整表示，不需要为 Web、kinematics 和 collision 重复三次。只有 Web
实际使用独立轻量 GLB，或 collision 使用独立简化体时，才写 `overrides`。

## `mesh_path` 的作用

`mesh_path` 很有用，但它是运行时注入的资产根，不是打包前替换的文本变量：

```xml
<xacro:macro name="szlab_mixer_robot" params="mesh_path prefix:=''">
  <link name="${prefix}rail">
    <visual>
      <geometry>
        <mesh filename="${mesh_path}/meshes/rail.stl"/>
      </geometry>
    </visual>
  </link>
</xacro:macro>
```

Edge 根据 Catalog 里的声明文件位置，把
`.../szlab_mixer_robot/models` 注入 `mesh_path`。这样 workspace、wheel 和缓存包只改变注入值，
Xacro 源文件完全相同。Web 获得的是 Edge 生成的资产 URL，不是这条服务器路径。

## Edge 目标读取方法

1. `unilab --workspace .` 读取根 `pyproject.toml`；
2. 定位唯一 import package `szlab_poly_studio`；
3. AST 递归扫描 `@device/@resource/@workflow_definition`；
4. 对每个模型按声明 Python 文件解析相对 `entry`；
5. 校验入口、include、mesh、texture、路径 containment 和 wheel package-data；
6. 把定义及资产闭包写进同一个 PackageCatalog；
7. Graph/Profile 选择设备后才 import 驱动；
8. 前端请求模型时，Edge 通过 Catalog 返回元数据和受控资产 URL；
9. Xacro consumer 以已校验模型目录作为 `mesh_path`。

发现模型不等于实例化设备，也不等于连接 PLC。AST 扫描和资产校验必须保持无副作用。

## 当前与目标的差距

SZLab 侧已经完成根单包、驱动归位、外形共置、装饰器绑定和 package-data；OS 侧仍需实现
Issue #147 的 PackageCatalogCompiler、`--workspace`、资产 Source Adapter 和 Edge asset API。
因此当前 `scripts/check-package.sh` 仍使用旧 `--devices` 做兼容 AST 检查，真实 3D Edge/Web
闭环要等 OS delivery 与第一套真实 Xacro/mesh 到位后验收。

## 第一套真实模型建议

优先选择 `szlab_mixer_robot` 做垂直闭环，因为它同时覆盖 Xacro、mesh、关节、碰撞、
`mesh_path` 和 Web：

1. 提交可再分发的 Xacro 与 mesh；
2. 补充装饰器的 `format/entry/macro`；
3. 从 clean wheel 编译 Catalog；
4. 比较 workspace 与 wheel Catalog；
5. 启动 Edge，验证模型资产 URL；
6. 验证 Web、kinematics、collision 都来自同一默认 Xacro；
7. 再评估是否真的需要独立 Web GLB 或 collision override。
