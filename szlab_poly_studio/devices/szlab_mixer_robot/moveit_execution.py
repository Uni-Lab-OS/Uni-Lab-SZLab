"""MoveIt execution Adapter for SZLab simulation and real-driver composition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import time
from typing import Any, Protocol
from uuid import uuid4

from szlab_poly_studio.devices.szlab_mixer_robot.execution_backend import (
    BackendCapabilities,
    BackendRejectedError,
    CompletionObservation,
    DispatchReceipt,
    DispatchState,
    DispatchUnknownError,
    ExecutionObservation,
    MotionSequence,
    ObservationState,
    ResolvedSiteAction,
    RobotCommand,
)


class MoveItJointClient(Protocol):
    def ready(self) -> bool: ...

    def wait_until_ready(self, timeout_sec: float = 180.0) -> bool: ...

    def execute_joint_target(
        self,
        *,
        planning_group: str,
        joint_names: Sequence[str],
        joint_positions: Sequence[float],
    ) -> bool: ...

    def current_joint_positions(
        self,
        joint_names: Sequence[str],
    ) -> Sequence[float]: ...


class SZLabMoveItExecutionAdapter:
    """MoveIt Adapter that never reads or fabricates PLC variables.

    A simulation profile uses only controller terminal state and final joint
    error as simulation evidence. It deliberately does not fabricate a gripper
    or attached-payload witness. Physical MoveIt remains fail-closed until a
    real HardwareProfile, readiness policy and tool Adapter are implemented.
    """

    backend_id = "szlab.moveit"

    def __init__(
        self,
        client: MoveItJointClient,
        *,
        site_targets: Mapping[str, Any],
        joint_names: Sequence[str],
        planning_group: str = "arm",
        binding_version: str,
        simulation_only: bool,
        final_joint_tolerance: float = 0.01,
        hardware_profile_ref: str = "szlab-mixer-moveit-sim@v1",
    ) -> None:
        self.client = client
        self.site_targets = dict(site_targets)
        self.joint_names = tuple(str(name) for name in joint_names)
        self.planning_group = planning_group
        self.binding_version = binding_version
        self.simulation_only = bool(simulation_only)
        self.final_joint_tolerance = float(final_joint_tolerance)
        if not self.simulation_only:
            raise BackendRejectedError(
                "当前 MoveIt package 只实现 mock_components 仿真；实机 HardwareProfile 尚未接入，按 fail-closed 拒绝"
            )
        if not math.isfinite(self.final_joint_tolerance) or self.final_joint_tolerance <= 0:
            raise ValueError("MoveIt final_joint_tolerance 必须是有限正数")
        self.hardware_profile_ref = str(hardware_profile_ref)
        profile_payload = {
            "profile": self.hardware_profile_ref,
            "environment": "simulation",
            "driver": "mock_components/GenericSystem",
            "joint_names": self.joint_names,
            "planning_group": self.planning_group,
        }
        self.hardware_profile_digest = hashlib.sha256(
            json.dumps(profile_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.backend_generation = str(uuid4())
        self.capabilities = BackendCapabilities(
            execution_environment="simulation",
            supports_controlled_cancel=False,
            supports_restart_reconcile=False,
        )

    def resolve(
        self,
        *,
        operation: str,
        command_id: str,
        target_site: str,
        material_id: str,
        program_version: str,
        point_set_version: str,
        payload_profile: str,
    ) -> ResolvedSiteAction:
        if operation not in {"pick", "place"}:
            raise ValueError(f"未知 MoveIt Site Action: {operation}")
        # Windows + full-station URDF 下 move_group 常需 1–2 分钟才 advertise
        # /move_action；立刻 ready() 会把 workflow job 打成失败。阻塞等待期间
        # 依赖全局 MultiThreadedExecutor 其它线程推进 discovery / joint_states。
        if not self.client.wait_until_ready(timeout_sec=180.0):
            raise BackendRejectedError(
                "MoveIt 或 joint_states 在 180s 内仍未就绪（/move_action 或 /joint_states）"
            )
        raw_site = self.site_targets.get(target_site)
        if not isinstance(raw_site, Mapping):
            raise ValueError(f"MoveIt 点位集没有 Site: {target_site}")
        raw_targets = raw_site.get(operation)
        if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes)):
            raise ValueError(f"MoveIt 点位集没有 {target_site} 的 {operation} 序列")
        targets = tuple(
            tuple(float(position) for position in target)
            for target in raw_targets
        )
        binding_digest = hashlib.sha256(
            json.dumps(
                {
                    "binding_version": self.binding_version,
                    "site": target_site,
                    "operation": operation,
                    "joint_names": self.joint_names,
                    "targets": targets,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        command = RobotCommand(
            command_id=command_id,
            instruction=MotionSequence(
                planning_group=self.planning_group,
                joint_names=self.joint_names,
                joint_targets=targets,
            ),
            program_version=program_version,
            point_set_version=point_set_version,
            payload_profile=payload_profile,
        )
        return ResolvedSiteAction(
            operation=operation,  # type: ignore[arg-type]
            target_site=target_site,
            material_id=material_id,
            backend_id=self.backend_id,
            backend_generation=self.backend_generation,
            hardware_profile_ref=self.hardware_profile_ref,
            hardware_profile_digest=self.hardware_profile_digest,
            execution_environment="simulation",
            binding_version=self.binding_version,
            binding_digest=binding_digest,
            command=command,
            completion_plan={
                "simulation_only": self.simulation_only,
                "tool_effect": "none",
                "final_joint_tolerance": self.final_joint_tolerance,
            },
        )

    def submit(self, command: RobotCommand) -> DispatchReceipt:
        instruction = command.instruction
        if not isinstance(instruction, MotionSequence):
            raise BackendRejectedError("MoveIt Adapter 只接受 MotionSequence")
        completed_segments = 0
        try:
            for target in instruction.joint_targets:
                success = self.client.execute_joint_target(
                    planning_group=instruction.planning_group,
                    joint_names=instruction.joint_names,
                    joint_positions=target,
                )
                if not success:
                    return DispatchReceipt(
                        DispatchState.SENT,
                        {
                            "success": False,
                            "completed_segments": completed_segments,
                            "segment_count": len(instruction.joint_targets),
                        },
                    )
                completed_segments += 1
        except Exception as exc:
            raise DispatchUnknownError(
                f"MoveIt 已进入派发阶段，执行结果不确定: {exc}"
            ) from exc
        return DispatchReceipt(
            DispatchState.SENT,
            {
                "success": True,
                "completed_segments": completed_segments,
                "segment_count": len(instruction.joint_targets),
            },
        )

    def observe(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation:
        instruction = command.instruction
        if not isinstance(instruction, MotionSequence):
            return ExecutionObservation(
                ObservationState.FAILED,
                "MoveIt Adapter 收到非 MotionSequence 命令",
            )
        if receipt is None or receipt.state is DispatchState.UNCERTAIN:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt dispatch receipt 缺失或不确定",
            )
        if receipt.state is DispatchState.NOT_SENT:
            return ExecutionObservation(
                ObservationState.FAILED,
                "MoveIt 明确未发送命令",
            )
        if not bool(receipt.output.get("success")):
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt 序列未全部完成；机械臂可能已经移动",
                dict(receipt.output),
            )
        try:
            actual = tuple(
                float(position)
                for position in self.client.current_joint_positions(
                    instruction.joint_names
                )
            )
        except Exception as exc:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                f"MoveIt 最终关节状态读取失败: {exc}",
            )
        expected = instruction.joint_targets[-1]
        if len(actual) != len(expected):
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt 最终关节状态维度不匹配",
                {"actual": actual, "expected": expected},
            )
        max_error = max(abs(left - right) for left, right in zip(actual, expected))
        if not all(math.isfinite(value) for value in actual) or not math.isfinite(max_error):
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt 最终关节状态包含 NaN/Inf",
                {"actual": actual, "expected": expected},
            )
        evidence = {
            "controller_terminal": "SUCCEEDED",
            "final_joint_positions": actual,
            "expected_joint_positions": expected,
            "max_joint_error": max_error,
        }
        if max_error > self.final_joint_tolerance:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt action 成功但最终关节误差超限",
                evidence,
            )
        return ExecutionObservation(
            ObservationState.SUCCEEDED,
            "MoveIt controller 终态与最终关节状态一致",
            evidence,
        )

    def verify(
        self,
        action: ResolvedSiteAction,
        execution: ExecutionObservation,
    ) -> CompletionObservation:
        if execution.state is not ObservationState.SUCCEEDED:
            return CompletionObservation(
                execution.state,
                execution.message,
                execution.evidence,
            )
        return CompletionObservation(
            ObservationState.SUCCEEDED,
            f"{action.operation} 点位运动仅由 MoveIt 仿真轨迹见证；未执行真实抓取/释放",
            {
                **dict(execution.evidence),
                "simulation_only": True,
                "production_inventory_commit_allowed": False,
                "tool_effect": "none",
            },
        )

    def reconcile(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation:
        if receipt is None:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "MoveIt 没有可关联到本命令的 receipt，禁止根据当前位置猜测成功",
            )
        return self.observe(command, receipt)

    def cancel(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> bool:
        del command, receipt
        raise BackendRejectedError("当前 MoveIt Adapter 不声明受控取消能力")


class UniLabOSMoveItJointClient:
    """Thin Adapter over the existing UniLabOS MoveIt2 client.

    Imports remain local so the PLC-only profile does not require ROS/MoveIt
    Python packages merely to import the SZLab device package.
    """

    def __init__(
        self,
        ros_node: Any,
        *,
        joint_names: Sequence[str],
        base_link_name: str,
        end_effector_name: str,
        planning_group: str,
        speed: float = 0.1,
        execution_timeout: float = 300.0,
    ) -> None:
        from unilabos.devices.ros_dev.moveit2 import MoveIt2

        prefix = f"{ros_node.device_id}_"
        self._joint_names = tuple(f"{prefix}{name}" for name in joint_names)
        self._moveit = MoveIt2(
            node=ros_node,
            joint_names=list(self._joint_names),
            base_link_name=f"{prefix}{base_link_name}",
            end_effector_name=f"{prefix}{end_effector_name}",
            group_name=f"{prefix}{planning_group}",
            callback_group=ros_node.callback_group,
            use_move_group_action=True,
            ignore_new_calls_while_executing=True,
        )
        bounded_speed = float(max(0.01, min(speed, 1.0)))
        self._moveit.max_velocity = bounded_speed
        self._moveit.max_acceleration = bounded_speed
        self._joint_state_max_age = 2.0
        self._execution_timeout = max(0.1, float(execution_timeout))
        self._ready_poll_period = 0.2

    def ready(self) -> bool:
        state = self._moveit.joint_state
        age = self._moveit.joint_state_age_seconds
        return (
            state is not None
            and age is not None
            and age <= self._joint_state_max_age
            and self._moveit.move_action_server_ready()
        )

    def wait_until_ready(self, timeout_sec: float = 180.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_sec))
        while True:
            if self.ready():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self._ready_poll_period)

    def execute_joint_target(
        self,
        *,
        planning_group: str,
        joint_names: Sequence[str],
        joint_positions: Sequence[float],
    ) -> bool:
        del planning_group, joint_names
        self._moveit.move_to_configuration(
            joint_positions=[float(value) for value in joint_positions],
            joint_names=list(self._joint_names),
        )
        return bool(
            self._moveit.wait_until_executed(
                timeout_sec=self._execution_timeout,
            )
        )

    def current_joint_positions(
        self,
        joint_names: Sequence[str],
    ) -> Sequence[float]:
        del joint_names
        state = self._moveit.joint_state
        if state is None:
            raise RuntimeError("尚未收到 /joint_states")
        positions = dict(zip(state.name, state.position))
        return tuple(float(positions[name]) for name in self._joint_names)


__all__ = [
    "MoveItJointClient",
    "SZLabMoveItExecutionAdapter",
    "UniLabOSMoveItJointClient",
]
