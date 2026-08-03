# SZLab Warehouse Site 与 PLC 映射确认稿

> 状态：PARTIALLY CONFIRMED / S2 已确认，S071 已按现有证据定案，S3/S11 产品类型仍待确认
> 日期：2026-08-03
> 目的：确认 Warehouse Site、Inventory Site、PLC 在位信号和机器人位置参数之间的映射。

## 1. 核对基线

运行语义基线采用 `origin/main@4682bb3`：

- `szlab_poly_studio/resources/warehouses.py`
- `szlab_poly_studio/resources/carriers/*.py`
- `deployment/graphs/szlab-local-debug.json`
- `szlab_poly_studio/devices/szlab_poly_plc/device.py`
- `szlab_poly_studio/devices/szlab_poly_plc/szlab_plc_0730.csv`

`origin/feat/szlab-material-display@28e6bc9` 的提交时间更新，包含新的 3D 资产和通用
`szlab_poly_beaker_warehouse` 类型，但它没有包含 `origin/main` 最新的启动图和 Workflow
修复。因此当前不存在一个同时包含两边最新内容的已提交分支。本稿使用 `origin/main` 的运行
语义，并交叉检查 material-display 分支的 Warehouse 几何和 Site 数量。

当前工作区的 Warehouse 定义与 `origin/main` 相同；本地启动图的 Warehouse、Site 和 110 个
容器物料与 `origin/main` 数量一致，主要差异是 registry class namespace 和其他设备节点。

### 1.1 启动图库存规模

| Warehouse instance | Site | `occupied_by` | 物料类型 |
|---|---:|---:|---|
| `s1_loading_buffer` | 6 | 6 | TIP box |
| `s2_tip_warehouse` | 6 | 6 | TIP box |
| `s3_unused_beaker` | 36 | 36 | 18×烧杯 + 18×500 mL 样品瓶 |
| `powder_container_warehouse` | 6 | 6 | 粉料容器 |
| `s10_liquid_reagent` | 20 | 20 | 100 mL 试剂瓶 |
| `s11_used_beaker` | 36 | 36 | 18×烧杯 + 18×500 mL 样品瓶 |
| **合计** | **110** | **110** | |

这个 JSON 是“全仓填充”的调试/展示库存。若真机现场不是全仓满载，不得把它原样作为生产
Inventory 初始事实；生产启动图必须按实际库存移除相应 `occupied_by` 和物料节点。

## 2. Site 的权威链路

### 2.1 Warehouse 初始化

Warehouse/ItemizedCarrier 初始化后已经具有：

- `_ordering`：Site label 到 holder 的有序映射；
- `child_locations`：Site 相对坐标；
- `child_size`：Site 尺寸；
- `sites`：当前 holder/occupant；
- `content_type`、`visible` 等序列化属性。

序列化到启动图后，这些信息位于 Warehouse node 的 `config.sites[]`。其中 `label` 是
Warehouse 内稳定的业务键，`occupied_by` 是启动时的逻辑占用关系。

### 2.2 Edge 本地查询

OS 启动后，Graph 只作为一次性输入；运行时权威是同一个可变 `ResourceTreeSet`。
`MaterialGraphCatalog` 把 Warehouse `config.sites[]` 投影为 Material Site：

- Site ID：由 graph identity、Warehouse node ID 和 Site label 确定性生成；
- owner：Warehouse 对应的 Material aggregate；
- occupant：由 `occupied_by` 解析为 Material UUID；
- geometry/content type：来自 Warehouse Site declaration。

前端通过 `GET /api/v1/materials?page=...` 获得 aggregate，现有 FE 会解析
`config.sites` 并展示安装位和占用数。对当前本地启动图实测可查询到 126 个 aggregate，
其中六个 Warehouse 合计 110 个 Site，110 个 Site 均有逻辑 occupant。

### 2.3 Backend Inventory

Backend 已有独立持久化 `Site` 实体，记录：

- `material_uuid`：拥有该 Site 的 Warehouse/Carrier Material；
- `name`、`sort_order`；
- `allowed_resource_template_uuids`；
- `occupied_material_uuid`；
- 几何位置和尺寸。

但当前缺少两段完整链路：

1. Deployment/Warehouse instance 激活时，将 Site declaration 幂等 materialize/upsert 为
   Backend Site rows；
2. 前端一次性查询 Backend 的 flat Site collection。当前 Backend 仅有
   `GET /api/v1/materials/{uuid}/sites`，FE 的 `getGraph()` 只读取 materials，不会逐个补取 Site。

目标链路应为：

```text
Warehouse Site declaration
  -> deployment activation/materialization
  -> Backend Material + Site rows
  -> GET /api/v1/sites（flat collection）
  -> FE 按 material_uuid 归组
```

Edge 本地的 `config.sites` 可保留为兼容投影，但不能成为与 Backend Site 并列的第二套可写
权威。PLC observation 也不能直接改写 `occupied_material_uuid`；它只提供 presence evidence。

## 3. SiteControlBinding 的归属

PLC 地址和机器人程序参数不是 Inventory Site 属性。它们属于 SZLab cell deployment 的
SiteControlBinding，使用 `(warehouse_instance_id, site_label)` 关联 Site declaration，materialize
后再解析到稳定 Site UUID。

每个 binding 至少包含：

```yaml
warehouse_instance_id: s3_unused_beaker
site_label: L1B1
observation:
  provider: szlab_poly_plc
  variable: 传感器状态_上位机[0].NO[6]
interaction:
  product_type: 1
  controller_position_key: 1-1
  controller_position_number: 1
```

运行时必须验证：

- Warehouse 的 Site 集合与 binding Site 集合完全相等或被显式标记为 `inventory_only`；
- 一个 PLC presence variable 只能绑定一个物理 Site；
- 一个 Site 的 sort order、PLC sensor order 和 robot position 是三个独立字段，禁止相互猜算；
- SiteControlBinding 解析为 RobotCommand 后，adapter 不再接收 Site、Material 或 SkillBinding。

## 4. 候选映射

### 4.1 S1 上料过渡仓：暂不绑定机器人/PLC Site

| Site labels | 数量 | 当前证据 | 结论 |
|---|---:|---|---|
| `L1C1..L1C3`, `L2C1..L2C3` | 6 | S01 robot action 只允许 position=1；`[3].NO[6]` 名义上是机械手产品检测，不是六个 Warehouse Site 的在位阵列 | 六个 Site 先标 `inventory_only`，不能猜成 S01 position 1..6 |

如果 S1 设备另有六个在位信号或上料索引表，需要补充现场 PLC 表后再绑定。

### 4.2 S2 TIP 仓：按 JSON Site 顺序映射 1..6（现场已确认）

顺序采用启动图 `config.sites[]` 和 `children[]` 的顺序：从低层到高层，每层从 C1 到 C2。
用户在 2026-08-03 确认该顺序；同时提供的两张 SZLab 3D 现场参考图显示 S2 为三层、每层
两位，图中由下到上分别标注 `T11/T12`、`T21/T22`、`T31/T32`，与启动图一致。

| Site | PLC/robot position | Presence variable |
|---|---:|---|
| `T11` | 1 | `传感器状态_上位机[0].NO[0]` |
| `T12` | 2 | `传感器状态_上位机[0].NO[1]` |
| `T21` | 3 | `传感器状态_上位机[0].NO[2]` |
| `T22` | 4 | `传感器状态_上位机[0].NO[3]` |
| `T31` | 5 | `传感器状态_上位机[0].NO[4]` |
| `T32` | 6 | `传感器状态_上位机[0].NO[5]` |

注意：最新 JSON 将 S2 描述为 3 层×2 位，但当前 `warehouses.py` 仍使用通用的 6×1×1
`warehouse_factory`。Warehouse 初始化实现必须改成与 JSON 和现场确认相同的 3×2 几何和
`T11..T32` label，避免代码初始化与启动图分叉。

本次确认确定了 Site label、层列关系、PLC/robot position 编号及候选 presence variable 的
静态映射。真机启用前仍须逐位放入/取出 TIP 盒，确认 `[0].NO[0..5]` 的实际变化与本表一一
对应；该动作属于映射验收，不再是编号设计决策。

### 4.3 S3 未使用容器仓：高置信度

Site label：

- `L{layer}B{column}`：500 mL 烧杯，`product_type=1`；
- `L{layer}A{column}`：500 mL 样品瓶，候选 `product_type=3`；
- `layer=1..3`，`column=1..6`。

映射规则：

```text
controller_position_key    = "{layer}-{column}"
controller_position_number = (layer - 1) * 6 + column
```

Presence variable：

- B 行按 `S3_UNUSED_BEAKER_SENSORS[controller_position_key]`；
- A 行按 `S3_UNUSED_SAMPLE_VIAL_SENSORS[controller_position_key]`。

边界样例：

| Site | type | key | number | Presence variable |
|---|---:|---|---:|---|
| `L1B1` | 1 | `1-1` | 1 | `[0].NO[6]` |
| `L3B6` | 1 | `3-6` | 18 | `[1].NO[7]` |
| `L1A1` | 3 | `1-1` | 1 | `[1].NO[8]` |
| `L3A6` | 3 | `3-6` | 18 | `[2].NO[9]` |

### 4.4 S071 固体粉桶堆栈机器人接口：位置采用紧凑编号 1..6

S07 在现场语义上应拆成三个概念：

- `powder_container_warehouse`：图中左侧 2 层×3 位的“固体粉桶堆栈”；
- `S071`：机械臂对该六位堆栈执行取/放粉罐时使用的 PLC/机器人子工位编号；
- `S07`：图中右侧带转盘的固体加料设备；其机器人产品交接接口在现有程序中称为 `S072`。

依据是：S071 动作明确叫“取/放粉罐”，读取粉桶堆栈六个 presence sensor，并写入
`S071取放料编号`；独立的 S07 设备动作则负责扫码、旋转到进料位和注粉。用户提供的现场
参考图也把左侧“固体粉桶堆栈”和右侧“S07 固体加料”标成两个物理对象。

Site label `L{layer}C{column}` 与 presence variable 的关系明确：

| Site | key | Presence variable | 采用 position | 当前代码 position |
|---|---|---|---:|---:|
| `L1C1` | `1-1` | `[3].NO[8]` | 1 | 1 |
| `L1C2` | `1-2` | `[3].NO[9]` | 2 | 2 |
| `L1C3` | `1-3` | `[3].NO[10]` | 3 | 3 |
| `L2C1` | `2-1` | `[3].NO[11]` | 4 | 7 |
| `L2C2` | `2-2` | `[3].NO[12]` | 5 | 8 |
| `L2C3` | `2-3` | `[3].NO[13]` | 6 | 9 |

采用值按 2 层×3 位紧凑编号。S07 专用传感器定义本身已经把六个粉桶位明确编号为 1..6；
当前 `robot_S07` 复用了服务于 S3/S11 每层 6 列的 `_slot_number()`，才导致第二层错误发送
7..9。这是跨工位复用编号公式造成的实现缺陷，不应上升为 Warehouse Site 语义。

实现时应由每个 SiteControlBinding 显式保存 `controller_position_number`，S071 不再调用通用
`_slot_number()`。真机启用前仍须以低速/单步模式验证 4、5、6 三个目标点，防止现场机器人
程序另有历史编号；若现场程序确实只接受 7..9，应修订部署 binding，而不是改变 Site label。

### 4.5 S10 试剂瓶仓：高置信度

Site label `R{row}C{column}`，`row=1..4`，`column=1..5`：

```text
controller_position_key    = "{row}-{column}"
controller_position_number = (row - 1) * 5 + column
presence_variable          = S10_LIQUID_REAGENT_SENSORS[key]
```

边界样例：

| Site | key | number | Presence variable |
|---|---|---:|---|
| `R1C1` | `1-1` | 1 | `[4].NO[12]` |
| `R1C5` | `1-5` | 5 | `[5].NO[0]` |
| `R2C1` | `2-1` | 6 | `[5].NO[1]` |
| `R4C5` | `4-5` | 20 | `[5].NO[15]` |

### 4.6 S11 使用后容器仓：高置信度

Site label、product type 和 position 规则与 S3 相同：

- B 行：500 mL 烧杯，`product_type=1`；
- A 行：500 mL 样品瓶，候选 `product_type=3`；
- number：`(layer - 1) * 6 + column`。

Presence variable 改用 S11 的两组：

| Site | type | key | number | Presence variable |
|---|---:|---|---:|---|
| `L1B1` | 1 | `1-1` | 1 | `[6].NO[0]` |
| `L3B6` | 1 | `3-6` | 18 | `[7].NO[1]` |
| `L1A1` | 3 | `1-1` | 1 | `[7].NO[2]` |
| `L3A6` | 3 | `3-6` | 18 | `[8].NO[3]` |

## 5. 映射覆盖结论

| 分类 | Site 数量 |
|---|---:|
| 已确认静态映射：S2 | 6 |
| 证据收敛后定案、待真机逐点验收：S071 | 6 |
| 高置信度 PLC binding：S3 + S10 + S11 | 92 |
| 无六位现场证据、暂定 inventory-only：S1 | 6 |
| **总计** | **110** |

候选配置可为 104 个 Site 生成互不重复的 PLC presence variable；S1 六个 Site 不生成
SiteControlBinding。

## 6. 确认后实施顺序

1. 将 material-display 的通用 beaker Warehouse/3D 资产合并到最新 main，生成一个真正统一的
   基线提交。
2. 修正 S2 Warehouse factory，使初始化结果、测试和 JSON 都是 `T11..T32`、3 层×2 位。
3. 新增 deployment-owned SiteControlBinding catalog；启动时与实际 Warehouse Site 集合做
   exact-set validation，缺项、重项或未知 Site 均拒绝启用机器人动作。
4. PLC stack observer 按 Site binding 重排 raw variables，向 OS 发布 Warehouse Site order 的
   observation array；传感器只提供 presence evidence。
5. Material Handling resolver 使用 Site UUID 查 binding，解析 Site Action 为 RobotCommand；
   PLC adapter 只接收 RobotCommand。
6. 增加 deployment Site materialization/upsert；Backend 提供 flat Site read collection，FE 一次
   查询并按 `material_uuid` 归组。
7. 保留两份启动数据：全仓 110 物料的 debug/display fixture，以及按现场真实占用生成的
   production inventory graph。

## 7. 现场确认状态

1. **已确认**：S2 的位置 1..6 依次对应 `T11,T12,T21,T22,T31,T32`。
2. **已按证据定案，待真机逐点验收**：S071 是固体粉桶堆栈的机器人接口，第二层采用紧凑
   编号 `4,5,6`；当前代码的 `7,8,9` 来自错误复用每层六列公式。
3. S3/S11 的 500 mL 样品瓶在机器人程序中是否确认为 `product_type=3`？

S2 可进入代码修正和逐位传感器验收；S071 可按 1..6 实现，但在逐点验收前不得开放自动
流程；S3/S11 的 product type 在确认前不接入真机执行路径。
