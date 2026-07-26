# 迁移档案

本目录只保存从 `styxhuang/Uni-Lab-OS@d58a8c0` 提取的历史输入与映射证据，不作为运行时
配置源。

- `manifest.yaml` 是 12 个已提交 local UI preset、6 个 legacy JSON 工作流与当前 Python
  工作流之间的权威映射。
- `legacy/ui-presets`、`legacy/runtime-configs`、`legacy/workflows` 和 `legacy/plc_csv`
  保持原始内容，便于审计，因此可能包含已经失效的本机绝对路径或旧端点。
- 生产包只使用 `packages/` 下的最新 CSV、Profile、设备实现和 Python 工作流。
- 未在当前工作区或定向浏览器/e2e 持久化位置发现可安全归属到该项目的活动
  `unilabos.workflowDraft`；因此迁移对象以已提交 preset/JSON 为准。

历史动作名 `auto-<method>` 已统一为 `<method>`。这是把工作流写成
`device("<device_id>").<method>(...)` 所必需的语法迁移，不改变相应设备方法。
