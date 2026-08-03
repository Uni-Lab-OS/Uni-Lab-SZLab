"""Wayfinder 目标入口。

粉桶的 MaterialSource 位于独立粉桶堆栈，不是预置在 S07；目标定义见
``szlab_poly_studio.workflows.s07_material_dosing``。当前 OS Catalog 尚未把
``host_node.transfer_resource`` 发布成可编排 Action，因此该目标暂不登记到
``package.yaml``；物理 pick/place 和 Host 记账顺序已冻结，不以跳过记账降级。
"""

from szlab_poly_studio.workflows.s07_material_dosing import s07_material_dosing

__all__ = ["s07_material_dosing"]
