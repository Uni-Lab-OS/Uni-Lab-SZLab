# SZLab device mesh assets

Drop per-device runtime models here, for example:

```text
devices/szlab_mixer_robot/macro_device.xacro
devices/szlab_mixer_robot/meshes/visual/...
devices/szlab_mixer_stirrer/model.glb
```

Paths must match `model_manifest.yaml` `representations.*.entry` values.
2.5D board rendering does **not** require these files; they are for 3D only.
