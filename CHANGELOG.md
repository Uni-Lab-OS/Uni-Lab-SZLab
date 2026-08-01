# Changelog

## Unreleased

- Converted the repository to one root distribution and one `szlab_poly_studio` import package.
- Moved device drivers under `devices/<device_id>/` and split AI4C into its own sibling repository.
- Bound model/shape assets directly to device and resource decorators.
- Removed the package-wide model provider and duplicate root Profile/spec copies.

## 0.1.0 - 2026-07-26

- Extracted SZLab polymer studio and AI4C drivers from the pinned `styx/dev` source.
- Added template v2 device specs, Profile v1 packages, 8 warehouses, 6 material types and a deck.
- Migrated 12 local UI presets and 6 legacy JSON workflows into 13 Python AST workflows.
- Added safe local deployment, latest frontend bridge startup, schema/registry/workflow tests and CI.
