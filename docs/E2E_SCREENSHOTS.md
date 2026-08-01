# SZLab 最新前端 E2E 截图

本页聚焦 SZLab 物料视图和一个代表性工作流。全部 13 个生产工作流截图见
[`ALL_WORKFLOW_SCREENSHOTS.md`](ALL_WORKFLOW_SCREENSHOTS.md)。

截图由 `uni-lab-fe@d734337f63da832c11d704013be0d80f98681116`、SZLab 独立 Profile、
`deployment/graphs/szlab-local-debug.json` 和 OfflineOS bridge 共同生成。浏览器视口为
1920×1200。

## Python 代码与节点画布

S04 机械臂—磁搅流程通过真实 `/api/v1/authoring/compile` 和
`/api/v1/workflows:validate` 接口，画布断言为 3 个节点、2 条控制边。

![SZLab Python 工作流与节点画布](screenshots/szlab-workflow-python-node-canvas.png)

## 2D 物料界面

2D 投影从 `/api/v1/materials` 加载 22 个 SZLab 聚合对象，不包含 AI4C 设备。

![SZLab 2D 物料界面](screenshots/szlab-materials-2d.png)

## 2.5D 物料界面

2.5D SVG 投影使用同一份 22 对象 Material Aggregate；截图选中了
`debug_beaker_500ml`，右侧 Inspector 展示其配置、世界坐标和 revision。

![SZLab 2.5D 物料界面](screenshots/szlab-materials-2_5d.png)

## 复现

先分别启动 SZLab bridge 与最新前端：

```bash
UNILAB_PYTHON=/home/changjunhan/.micromamba/envs/unilab/bin/python \
  ./scripts/start-authoring-bridge.sh

cd ../uni-lab-fe
pnpm --filter @unilab/kernel-web preview --host 127.0.0.1 --port 4173
```

再从本仓库运行：

```bash
./scripts/capture-szlab-e2e.sh
```

机器可读结果保存在
[`screenshots/szlab-e2e-result.json`](screenshots/szlab-e2e-result.json)。
E2E 请求中的工作流编译、编写校验、Canonical 校验和 Material API 均为 200，未出现未预期的
浏览器错误。当前 local bridge 尚不提供旧设备页使用的 `/api/v1/online-devices` 和
`/ws/device_status` 兼容端点；结果文件将对应的 404/403 单独记录为兼容性警告，它们不参与
工作流与物料界面的通过判定。
