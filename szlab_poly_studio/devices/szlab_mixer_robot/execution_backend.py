"""Backend-neutral mechanical-arm execution contracts.

The standard gateway owns command identity, persistence and retry semantics.
Resolution freezes Site/business intent into a vendor-neutral ``RobotCommand``;
an execution Adapter then accepts only that command.  Hardware addresses,
transport payloads and Site/Material semantics never cross that Seam.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable


class BackendRejectedError(RuntimeError):
    """The Adapter can prove that no motion was dispatched."""


class DispatchUnknownError(RuntimeError):
    """The command may have been dispatched and must never be auto-retried."""


class DispatchState(str, Enum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    UNCERTAIN = "UNCERTAIN"


class ObservationState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BackendCapabilities:
    """Facts the gateway may rely on; unsupported features stay fail-closed."""

    execution_environment: Literal["physical", "simulation"]
    supports_controlled_cancel: bool = False
    supports_restart_reconcile: bool = False


@dataclass(frozen=True)
class ProgramInvocation:
    """Invoke an approved, versioned controller/cell program."""

    program_ref: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    kind: Literal["program"] = "program"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "program_ref": self.program_ref,
            "arguments": dict(self.arguments),
        }


@dataclass(frozen=True)
class MotionSequence:
    """Execute approved joint targets in order through a motion planner."""

    planning_group: str
    joint_names: tuple[str, ...]
    joint_targets: tuple[tuple[float, ...], ...]
    kind: Literal["motion_sequence"] = "motion_sequence"

    def __post_init__(self) -> None:
        if not self.planning_group.strip():
            raise ValueError("planning_group 不能为空")
        if not self.joint_names:
            raise ValueError("joint_names 不能为空")
        if not self.joint_targets:
            raise ValueError("joint_targets 不能为空")
        width = len(self.joint_names)
        if any(len(target) != width for target in self.joint_targets):
            raise ValueError("每个 joint target 必须与 joint_names 等长")
        if any(
            not math.isfinite(float(position))
            for target in self.joint_targets
            for position in target
        ):
            raise ValueError("joint target 必须全部是有限数")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "planning_group": self.planning_group,
            "joint_names": list(self.joint_names),
            "joint_targets": [list(target) for target in self.joint_targets],
        }


RobotInstruction: TypeAlias = ProgramInvocation | MotionSequence


@dataclass(frozen=True)
class RobotCommand:
    """Fully resolved vendor-neutral instruction accepted by every Adapter."""

    command_id: str
    instruction: RobotInstruction
    program_version: str
    point_set_version: str
    payload_profile: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "instruction": self.instruction.to_dict(),
            "program_version": self.program_version,
            "point_set_version": self.point_set_version,
            "payload_profile": self.payload_profile,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RobotCommand":
        raw_instruction = value.get("instruction")
        if not isinstance(raw_instruction, Mapping):
            raise TypeError("RobotCommand.instruction 必须是对象")
        instruction_kind = str(raw_instruction.get("kind") or "")
        if instruction_kind == "program":
            raw_arguments = raw_instruction.get("arguments", {})
            if not isinstance(raw_arguments, Mapping):
                raise TypeError("ProgramInvocation.arguments 必须是对象")
            instruction: RobotInstruction = ProgramInvocation(
                program_ref=str(raw_instruction["program_ref"]),
                arguments=dict(raw_arguments),
            )
        elif instruction_kind == "motion_sequence":
            raw_names = raw_instruction.get("joint_names")
            raw_targets = raw_instruction.get("joint_targets")
            if not isinstance(raw_names, Sequence) or isinstance(raw_names, (str, bytes)):
                raise TypeError("MotionSequence.joint_names 必须是数组")
            if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes)):
                raise TypeError("MotionSequence.joint_targets 必须是数组")
            instruction = MotionSequence(
                planning_group=str(raw_instruction["planning_group"]),
                joint_names=tuple(str(name) for name in raw_names),
                joint_targets=tuple(
                    tuple(float(position) for position in target)
                    for target in raw_targets
                ),
            )
        else:
            raise ValueError(f"未知 RobotCommand instruction: {instruction_kind}")
        return cls(
            command_id=str(value["command_id"]),
            instruction=instruction,
            program_version=str(value["program_version"]),
            point_set_version=str(value["point_set_version"]),
            payload_profile=str(value["payload_profile"]),
        )


@dataclass(frozen=True)
class ResolvedSiteAction:
    """Frozen Site Action resolution retained for witness/audit, not dispatched."""

    operation: Literal["pick", "place"]
    target_site: str
    material_id: str
    backend_id: str
    backend_generation: str
    hardware_profile_ref: str
    hardware_profile_digest: str
    execution_environment: Literal["physical", "simulation"]
    binding_version: str
    binding_digest: str
    command: RobotCommand
    completion_plan: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "target_site": self.target_site,
            "material_id": self.material_id,
            "backend_id": self.backend_id,
            "backend_generation": self.backend_generation,
            "hardware_profile_ref": self.hardware_profile_ref,
            "hardware_profile_digest": self.hardware_profile_digest,
            "execution_environment": self.execution_environment,
            "binding_version": self.binding_version,
            "binding_digest": self.binding_digest,
            "command": self.command.to_dict(),
            "completion_plan": dict(self.completion_plan),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResolvedSiteAction":
        operation = str(value["operation"])
        if operation not in {"pick", "place"}:
            raise ValueError(f"未知 Site Action: {operation}")
        command = value.get("command")
        completion_plan = value.get("completion_plan", {})
        if not isinstance(command, Mapping) or not isinstance(completion_plan, Mapping):
            raise TypeError("ResolvedSiteAction command/completion_plan 必须是对象")
        execution_environment = str(value["execution_environment"])
        if execution_environment not in {"physical", "simulation"}:
            raise ValueError(
                f"未知 execution_environment: {execution_environment}"
            )
        return cls(
            operation=operation,  # type: ignore[arg-type]
            target_site=str(value["target_site"]),
            material_id=str(value["material_id"]),
            backend_id=str(value["backend_id"]),
            backend_generation=str(value["backend_generation"]),
            hardware_profile_ref=str(value["hardware_profile_ref"]),
            hardware_profile_digest=str(value["hardware_profile_digest"]),
            execution_environment=execution_environment,  # type: ignore[arg-type]
            binding_version=str(value["binding_version"]),
            binding_digest=str(value["binding_digest"]),
            command=RobotCommand.from_dict(command),
            completion_plan=dict(completion_plan),
        )


@dataclass(frozen=True)
class DispatchReceipt:
    state: DispatchState
    output: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state.value, "output": dict(self.output)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DispatchReceipt":
        output = value.get("output", {})
        if not isinstance(output, Mapping):
            raise TypeError("DispatchReceipt.output 必须是对象")
        return cls(state=DispatchState(str(value["state"])), output=dict(output))


@dataclass(frozen=True)
class ExecutionObservation:
    """Backend-only observation; it does not claim physical Material transfer."""

    state: ObservationState
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionObservation:
    """Combined execution and deployment witness decision."""

    state: ObservationState
    message: str
    witnesses: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class SiteActionResolver(Protocol):
    @property
    def backend_id(self) -> str: ...

    def resolve(
        self,
        *,
        operation: Literal["pick", "place"],
        command_id: str,
        target_site: str,
        material_id: str,
        program_version: str,
        point_set_version: str,
        payload_profile: str,
    ) -> ResolvedSiteAction: ...


@runtime_checkable
class RobotExecutionBackend(Protocol):
    """Seam implemented by PLC, vendor TCP/SDK, MoveIt and test Adapters."""

    @property
    def backend_id(self) -> str: ...

    @property
    def backend_generation(self) -> str: ...

    @property
    def hardware_profile_ref(self) -> str: ...

    @property
    def hardware_profile_digest(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    def submit(self, command: RobotCommand) -> DispatchReceipt: ...

    def observe(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation: ...

    def reconcile(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation: ...

    def cancel(self, command: RobotCommand, receipt: DispatchReceipt | None) -> bool: ...


@runtime_checkable
class CompletionVerifier(Protocol):
    def verify(
        self,
        action: ResolvedSiteAction,
        execution: ExecutionObservation,
    ) -> CompletionObservation: ...


@runtime_checkable
class RobotExecutionAdapter(
    SiteActionResolver,
    RobotExecutionBackend,
    CompletionVerifier,
    Protocol,
):
    """Composition convenience; the three smaller Interfaces remain the Seams."""


__all__ = [
    "BackendRejectedError",
    "BackendCapabilities",
    "CompletionObservation",
    "CompletionVerifier",
    "DispatchReceipt",
    "DispatchState",
    "DispatchUnknownError",
    "ExecutionObservation",
    "MotionSequence",
    "ObservationState",
    "ProgramInvocation",
    "ResolvedSiteAction",
    "RobotCommand",
    "RobotExecutionAdapter",
    "RobotExecutionBackend",
    "SiteActionResolver",
]
