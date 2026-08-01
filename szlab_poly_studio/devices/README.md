# Device layout

Each device owns one directory named after its stable `@device(id=...)` value. The
driver entry is `device.py`; protocol tables, calibration-independent defaults,
and model assets stay beside it.

```text
devices/<device_id>/
├── device.py
├── models/
│   ├── device.xacro       # add when a 3D model is available
│   ├── meshes/
│   └── shape.yml         # optional 2.5D fallback
└── ...                    # sensors, CSV tables, and helpers
```

Model metadata belongs in the device's `@device(model={...})` declaration. Paths
are relative to `device.py`. A single Xacro entry is the default source for Web,
kinematics, and collision; declare an override only when a genuinely different
optimized asset exists.
