"""Wayfinder 目标入口。

粉桶的 MaterialSource 位于独立粉桶堆栈，不是预置在 S07；正式定义见
``szlab_poly_studio.workflows.s07_material_dosing``。两个搬运分支并行就绪，
共享机械臂由 OS 设备锁串行执行，最后由固体称量节点汇合两条物料边。
"""

from szlab_poly_studio.workflows.s07_material_dosing import s07_material_dosing

__all__ = ["s07_material_dosing"]
