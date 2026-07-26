# Uni-Lab SZLab Integration

这是从 `styxhuang/Uni-Lab-OS` 的 `dev` 分支中拆出的独立维护仓库，集中维护：

- SZLab 聚合物工作站与 AI4C 的标准外部设备包；
- 8 个 warehouse、1 个 deck 和 6 类新增物料；
- Profile v1 与 device-template v2 设备契约；
- 从本地调试 UI preset/legacy JSON 迁移得到的 13 个 Python 工作流；
- 对接当前 Uni-Lab-OS local bridge 和最新 `uni-lab-fe` 的本地调试配置。

代码基线为 `styx/dev@d58a8c0d6de26b9de77161359bb627d75fa8e4e8`，结构与 schema 基线为
`Uni-Lab-Templates@5e44020e1020577b0c00ba196f82a7e434983b29`。完整来源见
[`NOTICE`](NOTICE)，迁移映射见 [`migration/manifest.yaml`](migration/manifest.yaml)。
本地联调证据与复现命令见 [`docs/VALIDATION.md`](docs/VALIDATION.md)。

## 两个独立设备包

本仓库采用 monorepo 管理，但 SZLab 和 AI4C 是两个互不交叉导入、可分别安装和发布的 Python
distribution：

| 包 | Distribution | Profile | 独立调试图 |
| --- | --- | --- | --- |
| SZLab | `unilabos-szlab-poly-studio` | `packages/szlab_poly_studio/package.yaml` | `deployment/graphs/szlab-local-debug.json` |
| AI4C | `unilabos-ai4c-robot` | `packages/ai4c_robot/package.yaml` | `deployment/graphs/ai4c-local-debug.json` |

分别检查和构建：

```bash
./scripts/check-szlab-package.sh
./scripts/check-ai4c-package.sh
./scripts/build-szlab-package.sh
./scripts/build-ai4c-package.sh
```

wheel 分别输出到 `dist/szlab/` 和 `dist/ai4c/`。

## 仓库结构

```text
packages/
  szlab_poly_studio/   # S1、S04-S09、机械臂、PLC、物料与 warehouse
  ai4c_robot/          # AI4C PLC 与机械臂
specs/                 # device-template v2 合同
schemas/               # 当前模板 schema 的固定副本
deployment/            # 默认不连接硬件的本地图和配置
migration/             # 原始 preset/JSON/CSV 与可审计映射
tests/                 # schema、注册表、物料、工作流和仓库卫生测试
```

## 环境与安装

必须使用可运行 Uni-Lab-OS 的 Python 3.11 环境。当前联调环境的示例：

```bash
export UNILAB_PYTHON=/home/changjunhan/.micromamba/envs/unilab/bin/python
"$UNILAB_PYTHON" -m pip install -e packages/szlab_poly_studio --no-deps
"$UNILAB_PYTHON" -m pip install -e packages/ai4c_robot --no-deps
```

`--no-deps` 适用于已经安装 Uni-Lab-OS 的环境；新环境应先按 Uni-Lab-OS 文档安装
`unilabos`、ROS 依赖和设备通信依赖。

## 设备包检查与测试

```bash
UNILAB_COMMAND=/home/changjunhan/.micromamba/envs/unilab/bin/unilab \
  ./scripts/check-packages.sh

PYTHONPATH="../Uni-Lab-OS:packages/szlab_poly_studio:packages/ai4c_robot" \
  /home/changjunhan/.micromamba/envs/unilab/bin/python -m pytest
```

`check-packages.sh` 使用模板仓库同样的 `--check_mode --external_devices_only` 入口。

## 最新前端本地联调

先启动只监听 loopback 的 authoring/runtime bridge。该模式加载两个 Profile、迁移后的动作目录和
本地物料图，执行由 OfflineOS 模拟，不连接 PLC：

```bash
UNILAB_PYTHON=/home/changjunhan/.micromamba/envs/unilab/bin/python \
  ./scripts/start-authoring-bridge.sh
```

然后在相邻的最新前端仓库启动 Web：

```bash
cd ../uni-lab-fe
pnpm dev
```

前端默认使用 `http://127.0.0.1:8014`。也可以访问
`?localOsUrl=http%3A%2F%2F127.0.0.1%3A8014` 显式指定。本地 bridge 提供的统一 v1
契约包括：

- `GET|PUT /api/v1/workflows/{id}/graph`
- `POST /api/v1/workflows:validate`
- `POST /api/v1/authoring/compile`
- `POST /api/v1/authoring/generate-python`
- `POST /api/v1/authoring/validate`
- `/api/v1/runtime/runs`、节点、事件、命令、取消与 WebSocket 投影
- `GET /api/v1/materials` 与 `GET /api/v1/material-models`

生产工作流源码位于两个包的 `workflows/` 下。工作流只经过 Uni-Lab-OS Python AST
编译器生成 Canonical v2，不使用 `eval` 或 `exec`。

只启动 SZLab 或 AI4C 时分别使用：

```bash
./scripts/start-szlab-authoring-bridge.sh
./scripts/start-ai4c-authoring-bridge.sh
```

SZLab 最新前端 E2E 截图见
[`docs/E2E_SCREENSHOTS.md`](docs/E2E_SCREENSHOTS.md)。

## OS 测试模式

需要验证真实 OS 注册、ResourceTreeSet 和 schedule 通道时，先运行
[`scripts/start-runtime-bridge.sh`](scripts/start-runtime-bridge.sh)，再运行
[`scripts/start-test-os.sh`](scripts/start-test-os.sh)。仓库提供的
[`local-debug.json`](deployment/graphs/local-debug.json) 对所有直连 OPC UA 驱动设置
`auto_connect: false`，S1 也禁止硬件动作。

真机接入前必须单独完成 IP、NodeId、账号、联锁、急停、物料占用和恢复语义核验；不得直接把
本地图中的 `auto_connect` 改为 `true` 后投入生产。

## 迁移说明

已提交的 12 个 local UI preset 全部映射到 Python 工作流。6 个 legacy JSON 工作流保留用于
动作序列回归，其中 S08 的 `sample_id: [a,b,c]` 通过标量适配动作表达，以满足当前 Python
AST 编译器的受限语法。历史 `auto-<method>` 动作统一迁移为 `<method>`，从而能写成合法的
`device("id").method(...)`。

当前工作区和定向浏览器/e2e 持久化位置没有发现可安全归属到本项目的活动
`unilabos.workflowDraft`，因此已提交的 preset 与 JSON 是本次迁移的权威输入。

## 许可

上游设备驱动标记为 DP Technology Proprietary License。本仓库应保持私有，除非权利人明确
授权再分发。详见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。
