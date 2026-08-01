# Resource layout

Resource factories live in this package and bind their assets directly through
`@resource(model={...})`. Resource-owned files use the stable resource ID:

```text
resources/<resource_id>/models/
├── resource.xacro         # add when a 3D model is available
├── meshes/
└── shape.yml             # optional 2.5D fallback
```

Model paths are relative to the Python file containing the decorator. There is no
package-wide model provider or model manifest.
