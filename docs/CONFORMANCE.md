# 接入规范与一致性说明

## 采用的基线

- 新设备来源：`https://github.com/styxhuang/Uni-Lab-OS`，
  `dev@d58a8c0d6de26b9de77161359bb627d75fa8e4e8`。
- 模板来源：`https://github.com/Uni-Lab-OS/Uni-Lab-Templates`，
  `main@5e44020e1020577b0c00ba196f82a7e434983b29`。
- `schemas/device-template-v2.schema.json` 与 `schemas/profile-v1.schema.json` 是上述模板提交的
  原样固定副本。
- 飞书接入规范：
  `https://dptechnology.feishu.cn/docx/YRZtdUKkJo1zu4xgjohcc498neh`。

飞书页面在本次环境中跳转企业登录，无法取得正文。为避免猜测，仓库把该限制写入
`migration/manifest.yaml`，并采用 `styx/dev` 自带的
`.cursor/skills/add-device/SKILL.md` 自包含规则与当前模板 schema 作为可验证基线。取得飞书
权限后，应将文档逐条复核结果追加到本文件，不应覆盖既有来源记录。

## 已落实的规则

- 每个设备使用 `@device`，设备动作使用 `@action`，状态属性使用
  `@property` + `@topic_config`。
- 动作名是稳定的英文 Python identifier；未继续使用 `auto-` 前缀。
- 新包不引用 `unilabos.devices.workstation.szlab_poly_studio` 私有内置路径。
- 设备参数保留单位语义，物料尺寸使用 mm，容积使用 μL。
- 外部包通过 `--devices <python-package> --external_devices_only` 检查。
- Profile 使用 `generic_plc_macro`、明确的 connection ref、资源拓扑和输入参数绑定。
- Profile/device spec 分别通过 Profile v1 和 device-template v2 schema。
- 本地调试图默认不连接 OPC UA，不包含凭据，不允许 S1 硬件动作。
- warehouse 和物料由 `@resource` 注册；运行时物料权威仍是 OS 的 ResourceTreeSet，前端只读其
  `/api/v1/materials` 投影。
- Python 工作流由受限 AST 编译器生成 Canonical v2；13 个工作流均有 source map 和真实动作
  目录校验。

## 包含的设备与资源

SZLab 包注册 9 个设备：PLC、S1、S04 磁搅、S05 拍照、S06 注射泵、机械臂、S07 固体加料、
S08 开关盖和 S09 移液。AI4C 包注册 PLC 与机械臂。

SZLab 包同时注册：

- 8 个 warehouse 工厂与 1 个聚合物工作站 deck；
- 500 mL 烧杯；
- 250 mL/500 mL 样品瓶；
- 100 mL 液体试剂瓶；
- 固体粉罐；
- 移液枪头。

## 验证入口

```bash
UNILAB_COMMAND=/path/to/unilab ./scripts/check-packages.sh
PYTHONPATH="../Uni-Lab-OS:packages/szlab_poly_studio:packages/ai4c_robot" \
  /path/to/python -m pytest
```

`tests/` 同时检查 schema、Profile 可加载性、装饰器注册表、warehouse 容量、物料单位、部署图
安全默认值、迁移覆盖率、legacy 动作序列和所有 Python 工作流的 AST 编译。
