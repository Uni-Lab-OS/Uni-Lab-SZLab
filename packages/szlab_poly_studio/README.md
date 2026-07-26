# SZLab Poly Studio device package

外部包入口为 `szlab_poly_studio/`。它维护聚合物工作站 PLC、S1、S04-S09、机械臂、deck、
warehouse、物料与迁移后的 Python 工作流。

检查：

```bash
unilab --check_mode --devices ./szlab_poly_studio --external_devices_only
```

`package.yaml` 是源码仓库的 Profile v1 入口，`szlab_poly_studio/profile/` 是随 wheel 分发的
Profile/device spec 副本。生产使用前请遵守仓库根目录的真机接入清单。
