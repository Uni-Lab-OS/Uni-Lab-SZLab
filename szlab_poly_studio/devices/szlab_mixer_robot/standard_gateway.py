from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from szlab_poly_studio.common.site_control_bindings import (
    SiteControlBinding,
    canonical_site_reference,
    resolve_canonical_site_reference,
    resolve_robot_site_reference,
)
from szlab_poly_studio.devices.szlab_mixer_robot.execution_backend import (
    BackendCapabilities,
    BackendRejectedError,
    CompletionObservation,
    DispatchReceipt,
    DispatchState,
    DispatchUnknownError,
    ExecutionObservation,
    ObservationState,
    ProgramInvocation,
    ResolvedSiteAction,
    RobotCommand,
    RobotExecutionAdapter,
)
from szlab_poly_studio.devices.szlab_mixer_robot.robot_tasks import (
    ROBOT_HOME_VARIABLE,
    ROBOT_WRITE_ALLOWED_VARIABLE,
    build_variables,
)

TOOL_PAYLOAD_SENSOR_VARIABLE = "传感器状态_上位机[3].NO[6]"
PLC_HARDWARE_PROFILE_REF = "szlab-mixer-plc-program@v1"
PLC_HARDWARE_PROFILE_DIGEST = hashlib.sha256(
    json.dumps(
        {
            "profile": PLC_HARDWARE_PROFILE_REF,
            "driver": "plc-program-handshake",
            "environment": "physical",
        },
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


class CommandState(str, Enum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"

    @property
    def terminal(self) -> bool:
        return self in {
            CommandState.SUCCEEDED,
            CommandState.FAILED,
            CommandState.CANCELED,
            CommandState.REJECTED,
        }


@dataclass(frozen=True)
class StandardRobotRequest:
    kind: Literal["pick", "place"]
    command_id: str
    site: str
    program_version: str
    point_set_version: str
    payload_profile: str
    source_boot_id: str
    monotonic_sequence: int
    material_context: Mapping[str, Any]
    source: str = "unilabos"
    protocol_version: str = "unilab.robot/v1"
    backend_id: str = "szlab.plc-program"
    hardware_profile_ref: str = PLC_HARDWARE_PROFILE_REF
    hardware_profile_digest: str = PLC_HARDWARE_PROFILE_DIGEST
    execution_environment: Literal["physical", "simulation"] = "physical"

    def __post_init__(self) -> None:
        required = {
            "command_id": self.command_id,
            "site": self.site,
            "program_version": self.program_version,
            "point_set_version": self.point_set_version,
            "payload_profile": self.payload_profile,
            "source_boot_id": self.source_boot_id,
            "backend_id": self.backend_id,
            "hardware_profile_ref": self.hardware_profile_ref,
            "hardware_profile_digest": self.hardware_profile_digest,
            "execution_environment": self.execution_environment,
        }
        missing = [name for name, value in required.items() if not isinstance(value, str) or not value.strip()]
        if missing:
            raise ValueError(f"标准机械臂请求缺少字段: {', '.join(missing)}")
        if self.execution_environment not in {"physical", "simulation"}:
            raise ValueError("execution_environment 只能是 physical/simulation")
        if len(self.command_id) > 128:
            raise ValueError("command_id 长度不能超过 128")
        if (
            isinstance(self.monotonic_sequence, bool)
            or not isinstance(self.monotonic_sequence, int)
            or not 1 <= self.monotonic_sequence <= 2**63 - 1
        ):
            raise ValueError("monotonic_sequence 必须是 1..2^63-1 的整数")
        if not isinstance(self.material_context, Mapping):
            raise TypeError("material_context 必须是对象")
        json.dumps(_jsonable(self.material_context), ensure_ascii=False, sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "command_id": self.command_id,
            "site": self.site,
            "program_version": self.program_version,
            "point_set_version": self.point_set_version,
            "payload_profile": self.payload_profile,
            "source_boot_id": self.source_boot_id,
            "monotonic_sequence": self.monotonic_sequence,
            "material_context": _jsonable(self.material_context),
            "source": self.source,
            "protocol_version": self.protocol_version,
            "backend_id": self.backend_id,
            "hardware_profile_ref": self.hardware_profile_ref,
            "hardware_profile_digest": self.hardware_profile_digest,
            "execution_environment": self.execution_environment,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommandRecord:
    request_hash: str
    request: Mapping[str, Any]
    state: CommandState
    boot_id: str
    message: str
    output: Mapping[str, Any]

    def public_result(self) -> dict[str, Any]:
        raw_action = self.output.get("resolved_site_action")
        environment = "physical"
        if isinstance(raw_action, Mapping):
            environment = str(raw_action.get("execution_environment") or environment)
        succeeded = self.state is CommandState.SUCCEEDED
        return {
            "command_id": str(self.request["command_id"]),
            "state": self.state.value,
            "success": succeeded,
            "message": self.message,
            "boot_id": self.boot_id,
            "execution_environment": environment,
            "inventory_commit_allowed": succeeded and environment == "physical",
        }


class CommandConflictError(RuntimeError):
    pass


class CommandSequenceError(RuntimeError):
    pass


class CommandUnresolvedError(RuntimeError):
    pass


class SZLabRobotCommandJournal:
    """Small durable boundary for the legacy PLC adapter.

    It deliberately mirrors the mechanical-arm repository's command semantics:
    persist before dispatch, exact replay by command_id, and no automatic resend
    after an UNKNOWN result.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS szlab_robot_commands_v1 (
                    command_id TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    boot_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS szlab_robot_source_epochs_v1 (
                    source TEXT NOT NULL,
                    source_boot_id TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL,
                    active INTEGER NOT NULL,
                    PRIMARY KEY (source, source_boot_id)
                )
                """
            )

    def accept(self, request: StandardRobotRequest, boot_id: str) -> tuple[bool, CommandRecord]:
        request_json = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True)
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM szlab_robot_commands_v1 WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            if row is not None:
                record = _record_from_row(row)
                if record.request_hash != request.fingerprint():
                    raise CommandConflictError(f"command_id {request.command_id} 已被不同请求占用")
                connection.commit()
                return False, record

            unresolved = connection.execute(
                """
                SELECT command_id FROM szlab_robot_commands_v1
                WHERE state IN (?, ?, ?)
                LIMIT 1
                """,
                (
                    CommandState.ACCEPTED.value,
                    CommandState.RUNNING.value,
                    CommandState.UNKNOWN.value,
                ),
            ).fetchone()
            if unresolved is not None:
                raise CommandUnresolvedError(
                    "存在未完成 ACCEPTED/RUNNING/UNKNOWN 命令，禁止新运动: "
                    f"{unresolved['command_id']}"
                )

            self._advance_sequence(connection, request)
            connection.execute(
                """
                INSERT INTO szlab_robot_commands_v1 (
                    command_id, request_hash, request_json, state, boot_id,
                    message, output_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.command_id,
                    request.fingerprint(),
                    request_json,
                    CommandState.ACCEPTED.value,
                    boot_id,
                    "命令已登记，尚未下发",
                    "{}",
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM szlab_robot_commands_v1 WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            connection.commit()
            assert row is not None
            return True, _record_from_row(row)

    @staticmethod
    def _advance_sequence(connection: sqlite3.Connection, request: StandardRobotRequest) -> None:
        epoch = connection.execute(
            """
            SELECT last_sequence, active
            FROM szlab_robot_source_epochs_v1
            WHERE source = ? AND source_boot_id = ?
            """,
            (request.source, request.source_boot_id),
        ).fetchone()
        if epoch is not None:
            if not bool(epoch["active"]):
                raise CommandSequenceError(f"来源 {request.source} 使用了已退役 source_boot_id")
            if request.monotonic_sequence <= int(epoch["last_sequence"]):
                raise CommandSequenceError("monotonic_sequence 未单调递增")
            connection.execute(
                """
                UPDATE szlab_robot_source_epochs_v1
                SET last_sequence = ?
                WHERE source = ? AND source_boot_id = ?
                """,
                (request.monotonic_sequence, request.source, request.source_boot_id),
            )
            return

        connection.execute(
            "UPDATE szlab_robot_source_epochs_v1 SET active = 0 WHERE source = ?",
            (request.source,),
        )
        connection.execute(
            """
            INSERT INTO szlab_robot_source_epochs_v1 (
                source, source_boot_id, last_sequence, active
            ) VALUES (?, ?, ?, 1)
            """,
            (request.source, request.source_boot_id, request.monotonic_sequence),
        )

    def get(self, command_id: str) -> CommandRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM szlab_robot_commands_v1 WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            return _record_from_row(row) if row is not None else None

    def update(
        self,
        command_id: str,
        state: CommandState,
        boot_id: str,
        message: str,
        output: Mapping[str, Any] | None = None,
    ) -> CommandRecord:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE szlab_robot_commands_v1
                SET state = ?, boot_id = ?, message = ?, output_json = ?, updated_at = ?
                WHERE command_id = ?
                """,
                (
                    state.value,
                    boot_id,
                    message,
                    json.dumps(_jsonable(output or {}), ensure_ascii=False, sort_keys=True),
                    time.time(),
                    command_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"命令不存在: {command_id}")
            row = connection.execute(
                "SELECT * FROM szlab_robot_commands_v1 WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            assert row is not None
            return _record_from_row(row)

    def has_unresolved(self) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM szlab_robot_commands_v1
                WHERE state IN (?, ?, ?)
                LIMIT 1
                """,
                (
                    CommandState.ACCEPTED.value,
                    CommandState.RUNNING.value,
                    CommandState.UNKNOWN.value,
                ),
            ).fetchone()
            return row is not None

    def mark_previous_boot_inflight_unknown(self, current_boot_id: str) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE szlab_robot_commands_v1
                SET state = ?, message = ?, updated_at = ?
                WHERE state IN (?, ?) AND boot_id <> ?
                """,
                (
                    CommandState.UNKNOWN.value,
                    "驱动已重启，原执行结果必须对账，禁止自动重发",
                    time.time(),
                    CommandState.ACCEPTED.value,
                    CommandState.RUNNING.value,
                    current_boot_id,
                ),
            )
            return cursor.rowcount


class SZLabPLCExecutionAdapter:
    """Existing PLC program handshake behind the shared execution Interfaces.

    The owner may reach the PLC through OPC-UA, a TCP wrapper or a test channel;
    that transport choice stays below this Adapter and does not change the
    standard ``pick``/``place`` contract.
    """

    backend_id = "szlab.plc-program"

    def __init__(
        self,
        owner: Any,
        *,
        permit_asserts_remote_auto: bool,
        permit_asserts_safety_normal: bool,
        motion_permit_variable: str,
        tool_payload_sensor_variable: str,
    ):
        self.owner = owner
        self.permit_asserts_remote_auto = bool(permit_asserts_remote_auto)
        self.permit_asserts_safety_normal = bool(permit_asserts_safety_normal)
        self.motion_permit_variable = motion_permit_variable
        self.tool_payload_sensor_variable = tool_payload_sensor_variable
        self.backend_generation = str(uuid4())
        self.capabilities = BackendCapabilities(
            execution_environment="physical",
            supports_controlled_cancel=False,
            supports_restart_reconcile=False,
        )
        self.hardware_profile_ref = PLC_HARDWARE_PROFILE_REF
        self.hardware_profile_digest = PLC_HARDWARE_PROFILE_DIGEST
        self._resolved_bindings: dict[str, SiteControlBinding] = {}

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
    ) -> ResolvedSiteAction:
        self._validate_readiness(operation)
        binding = resolve_canonical_site_reference(target_site)
        if not binding.robot_action_ready:
            raise ValueError(
                binding.blocked_reason
                or f"Site {target_site} 尚未启用标准机械臂动作"
            )
        expected_payload = _payload_profile_for_site(binding)
        if payload_profile != expected_payload:
            raise ValueError(
                f"Site {canonical_site_reference(binding)} 要求负载 {expected_payload}, "
                f"实际为 {payload_profile}"
            )

        station = binding.station
        skill_station = station.lower()
        program_ref = (
            f"pick_from_{skill_station}"
            if operation == "pick"
            else f"place_to_{skill_station}"
        )
        arguments = _plc_program_arguments(binding)
        command = RobotCommand(
            command_id=command_id,
            instruction=ProgramInvocation(program_ref, arguments),
            program_version=program_version,
            point_set_version=point_set_version,
            payload_profile=payload_profile,
        )
        binding_digest = hashlib.sha256(
            json.dumps(
                {
                    "binding_version": point_set_version,
                    "site": canonical_site_reference(binding),
                    "station": binding.station,
                    "controller_position": binding.controller_position,
                    "presence_variable": binding.presence_variable,
                    "program_ref": program_ref,
                    "arguments": arguments,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self._resolved_bindings[command_id] = binding
        return ResolvedSiteAction(
            operation=operation,
            target_site=canonical_site_reference(binding),
            material_id=material_id,
            backend_id=self.backend_id,
            backend_generation=self.backend_generation,
            hardware_profile_ref=self.hardware_profile_ref,
            hardware_profile_digest=self.hardware_profile_digest,
            execution_environment="physical",
            binding_version=point_set_version,
            binding_digest=binding_digest,
            command=command,
            completion_plan={
                "site_sensor": binding.presence_variable,
                "tool_sensor": self.tool_payload_sensor_variable,
                "robot_home_variable": ROBOT_HOME_VARIABLE,
                "expected_site_present": operation == "place",
                "expected_tool_holding": operation == "pick",
            },
        )

    def _validate_readiness(self, operation: Literal["pick", "place"]) -> None:
        if not self.permit_asserts_remote_auto:
            raise BackendRejectedError(
                "未声明运动许可同时见证 REMOTE_AUTO，按 fail-closed 拒绝"
            )
        if not self.permit_asserts_safety_normal:
            raise BackendRejectedError(
                "未声明运动许可同时见证安全状态可运动，按 fail-closed 拒绝"
            )
        if not self.motion_permit_variable:
            raise BackendRejectedError("未配置现有 PLC/机器人运动许可变量")
        if not bool(
            self.owner._read_variable(self.motion_permit_variable, use_cache=False)
        ):
            raise BackendRejectedError(
                f"运动许可被拒绝: {self.motion_permit_variable}"
            )
        if not bool(self.owner._read_variable(ROBOT_HOME_VARIABLE, use_cache=False)):
            raise BackendRejectedError("Robot_Home 未确认")
        tool_holding = bool(
            self.owner._read_variable(
                self.tool_payload_sensor_variable,
                use_cache=False,
            )
        )
        if operation == "pick" and tool_holding:
            raise BackendRejectedError("pick 前机械手夹爪已有物料")
        if operation == "place" and not tool_holding:
            raise BackendRejectedError("place 前机械手夹爪未见证持料")

    def submit(self, command: RobotCommand) -> DispatchReceipt:
        instruction = command.instruction
        if not isinstance(instruction, ProgramInvocation):
            raise BackendRejectedError("PLC Adapter 只接受 ProgramInvocation")
        binding = self._resolved_bindings.get(command.command_id)
        if binding is None:
            raise BackendRejectedError("PLC 命令缺少本次启动中冻结的 SiteAccessBinding")
        try:
            result = self._execute_legacy(binding, instruction)
        except (BackendRejectedError, DispatchUnknownError):
            raise
        except Exception as exc:
            raise DispatchUnknownError(f"PLC 派发后结果不确定: {exc}") from exc

        if not isinstance(result, Mapping):
            return DispatchReceipt(
                DispatchState.UNCERTAIN,
                {"legacy_result": _jsonable(result)},
            )
        state = (
            DispatchState.NOT_SENT
            if not bool(result.get("success"))
            and result.get("status") == "rejected"
            else DispatchState.SENT
        )
        return DispatchReceipt(state, {"legacy_result": _jsonable(result)})

    def _execute_legacy(
        self,
        binding: SiteControlBinding,
        instruction: ProgramInvocation,
    ) -> Any:
        operation = "pick" if instruction.program_ref.startswith("pick_from_") else "place"
        if operation == "place" and not instruction.program_ref.startswith("place_to_"):
            raise BackendRejectedError(
                f"PLC program_ref 不受支持: {instruction.program_ref}"
            )
        if binding.station == "S071":
            return self._execute_s071(binding, operation)

        runner_name = f"_run_{binding.station.lower()}_{operation}"
        runner = getattr(self.owner, runner_name, None)
        if not callable(runner):
            raise BackendRejectedError(f"标准命令没有 Legacy PLC runner: {runner_name}")
        parameters = dict(instruction.arguments)
        inspect.signature(runner).bind(**parameters)
        result = runner(**parameters)
        if not isinstance(result, Mapping):
            return result
        witness_key = (
            "source_sensor_variable"
            if operation == "pick"
            else "target_sensor_variable"
        )
        if witness_key in result or not binding.presence_variable:
            return result
        return {**result, witness_key: binding.presence_variable}

    def _execute_s071(
        self,
        binding: SiteControlBinding,
        operation: Literal["pick", "place"],
    ) -> Mapping[str, Any]:
        """标准路径按 2×3 紧凑编号下发；不改变 Legacy `_slot_number`。"""

        is_pick = operation == "pick"
        sensor = binding.presence_variable
        return self.owner._submit_robot_task(
            task=operation,
            station="S071",
            task_number=14 if is_pick else 13,
            variables=build_variables(
                "pick_from_s071" if is_pick else "place_to_s071",
                S071取放料编号=binding.controller_position,
            ),
            reset_variables={"S071取放料编号": 0, "任务号": 0},
            precheck=lambda: self.owner._ensure_sensor_gate(
                sensor,
                is_pick,
                "S071 取粉罐源位必须有粉罐"
                if is_pick
                else "S071 放粉罐目标位必须为空",
            ),
            position=binding.site_label,
            controller_position=binding.controller_position,
            **(
                {"source_sensor_variable": sensor}
                if is_pick
                else {"target_sensor_variable": sensor}
            ),
        )

    def observe(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation:
        if receipt is None or receipt.state is DispatchState.UNCERTAIN:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "PLC 派发状态不确定，禁止自动重发",
            )
        legacy_result = receipt.output.get("legacy_result")
        if receipt.state is DispatchState.NOT_SENT:
            message = (
                str(legacy_result.get("message"))
                if isinstance(legacy_result, Mapping)
                else "PLC 明确拒绝命令"
            )
            return ExecutionObservation(ObservationState.FAILED, message)
        if not isinstance(legacy_result, Mapping):
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "PLC 返回值不是对象，无法确认控制器终态",
            )
        if not bool(legacy_result.get("success")):
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                str(legacy_result.get("message") or "PLC 未确认动作成功"),
                {"legacy_result": dict(legacy_result)},
            )
        return ExecutionObservation(
            ObservationState.SUCCEEDED,
            "PLC 程序报告完成",
            {
                "completion_value": _jsonable(
                    legacy_result.get("completion_value")
                )
            },
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
        plan = action.completion_plan
        site_sensor = str(plan.get("site_sensor") or "")
        if not site_sensor:
            return CompletionObservation(
                ObservationState.UNKNOWN,
                f"{action.operation} 缺少工位物料见证变量",
            )
        try:
            site_present = bool(
                self.owner._read_variable(site_sensor, use_cache=False)
            )
            tool_sensor = str(plan["tool_sensor"])
            tool_holding = bool(
                self.owner._read_variable(tool_sensor, use_cache=False)
            )
            robot_home_variable = str(plan["robot_home_variable"])
            robot_home = bool(
                self.owner._read_variable(robot_home_variable, use_cache=False)
            )
        except Exception as exc:
            return CompletionObservation(
                ObservationState.UNKNOWN,
                f"完成后见证读取失败: {exc}",
            )

        expected_site = bool(plan["expected_site_present"])
        expected_tool = bool(plan["expected_tool_holding"])
        witnesses = {
            "backend": self.backend_id,
            "site_sensor": site_sensor,
            "site_present": site_present,
            "expected_site_present": expected_site,
            "tool_sensor": tool_sensor,
            "tool_holding": tool_holding,
            "expected_tool_holding": expected_tool,
            "robot_home": robot_home,
            **dict(execution.evidence),
        }
        if site_present != expected_site or tool_holding != expected_tool or not robot_home:
            return CompletionObservation(
                ObservationState.UNKNOWN,
                f"{action.operation} 完成见证不一致，保持 UNKNOWN，禁止自动重发",
                witnesses,
            )
        return CompletionObservation(
            ObservationState.SUCCEEDED,
            f"{action.operation} 已由 PLC、工位在位、夹爪和 Robot_Home 共同见证",
            witnesses,
        )

    def reconcile(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> ExecutionObservation:
        if receipt is None:
            return ExecutionObservation(
                ObservationState.UNKNOWN,
                "PLC 协议没有本命令的 controller identity/receipt，禁止仅凭当前传感器猜测成功",
            )
        return self.observe(command, receipt)

    def cancel(
        self,
        command: RobotCommand,
        receipt: DispatchReceipt | None,
    ) -> bool:
        del command, receipt
        raise BackendRejectedError("当前 PLC 程序握手不声明受控取消能力")


class SZLabStandardRobotGateway:
    """Durable standard pick/place façade over a composed execution Adapter."""

    def __init__(
        self,
        owner: Any,
        *,
        journal_path: str,
        program_version: str,
        point_set_version: str,
        payload_profiles: list[str],
        actions_enabled: bool,
        permit_asserts_remote_auto: bool,
        permit_asserts_safety_normal: bool,
        motion_permit_variable: str = ROBOT_WRITE_ALLOWED_VARIABLE,
        tool_payload_sensor_variable: str = TOOL_PAYLOAD_SENSOR_VARIABLE,
        execution_identity_provider: Callable[[], Mapping[str, str]] | None = None,
        execution_backend: RobotExecutionAdapter | None = None,
    ):
        self.owner = owner
        self.program_version = program_version
        self.point_set_version = point_set_version
        self.payload_profiles = frozenset(payload_profiles)
        self.actions_enabled = bool(actions_enabled)
        self.execution_identity_provider = (
            execution_identity_provider or _capture_workflow_execution_identity
        )
        self.boot_id = str(uuid4())
        self._motion_lock = threading.RLock()
        self._sequence = time.monotonic_ns()
        self.journal = SZLabRobotCommandJournal(journal_path)
        composition: RobotExecutionAdapter = execution_backend or SZLabPLCExecutionAdapter(
            owner,
            permit_asserts_remote_auto=permit_asserts_remote_auto,
            permit_asserts_safety_normal=permit_asserts_safety_normal,
            motion_permit_variable=motion_permit_variable,
            tool_payload_sensor_variable=tool_payload_sensor_variable,
        )
        self.resolver = composition
        self.backend = composition
        self.completion_verifier = composition
        self.journal.mark_previous_boot_inflight_unknown(self.boot_id)

    def replace_backend(self, backend: RobotExecutionAdapter) -> None:
        """Composition hook used before actions start; never a runtime fallback."""

        with self._motion_lock:
            if self.journal.has_unresolved():
                raise RuntimeError("存在 ACCEPTED/RUNNING/UNKNOWN 命令时禁止切换机械臂执行 Adapter")
            self.resolver = backend
            self.backend = backend
            self.completion_verifier = backend

    def execute_site(
        self,
        *,
        kind: Literal["pick", "place"],
        resource: Any,
        warehouse: Any,
        site: str,
    ) -> dict[str, Any]:
        """由 WorkflowNodeJob 身份和最小业务参数生成可重放请求。"""

        try:
            workflow_identity = self.execution_identity_provider()
            command_id = _workflow_node_command_id(workflow_identity)
            binding = resolve_robot_site_reference(warehouse, site)
            canonical_site = canonical_site_reference(binding)
            payload_profile = _payload_profile_for_resource(resource)
            _resource_reference(warehouse, field_name="warehouse")
        except (TypeError, ValueError) as exc:
            return _public_rejection("", self.boot_id, str(exc))

        existing = self.journal.get(command_id)
        if existing is None:
            self._sequence += 1
            source_boot_id = self.boot_id
            sequence = self._sequence
        else:
            source_boot_id = str(existing.request["source_boot_id"])
            sequence = int(existing.request["monotonic_sequence"])

        request = StandardRobotRequest(
            kind=kind,
            command_id=command_id,
            site=canonical_site,
            program_version=self.program_version,
            point_set_version=self.point_set_version,
            payload_profile=payload_profile,
            source_boot_id=source_boot_id,
            monotonic_sequence=sequence,
            material_context={
                "resource": resource,
                "warehouse": warehouse,
                "workflow_identity": dict(workflow_identity),
            },
            source="unilabos-workflow-node-job",
            backend_id=self.backend.backend_id,
            hardware_profile_ref=str(self.backend.hardware_profile_ref),
            hardware_profile_digest=str(self.backend.hardware_profile_digest),
            execution_environment=(
                self.backend.capabilities.execution_environment
            ),
        )
        return self.execute(request)

    def execute_simulation_site(
        self,
        *,
        kind: Literal["pick", "place"],
        target_site: str,
        payload_profile: str,
        fixture_id: str,
    ) -> dict[str, Any]:
        """Execute motion-only simulation without accepting production Material."""

        if self.backend.capabilities.execution_environment != "simulation":
            return _public_rejection(
                "",
                self.boot_id,
                "simulation site motion 只允许 simulation HardwareProfile",
            )
        try:
            workflow_identity = self.execution_identity_provider()
            command_id = _workflow_node_command_id(workflow_identity)
            canonical_site = canonical_site_reference(
                resolve_canonical_site_reference(target_site)
            )
            normalized_fixture = str(fixture_id).strip()
            if not normalized_fixture:
                raise ValueError("simulation fixture_id 不能为空")
        except (TypeError, ValueError) as exc:
            return _public_rejection("", self.boot_id, str(exc))

        existing = self.journal.get(command_id)
        if existing is None:
            self._sequence += 1
            source_boot_id = self.boot_id
            sequence = self._sequence
        else:
            source_boot_id = str(existing.request["source_boot_id"])
            sequence = int(existing.request["monotonic_sequence"])
        return self.execute(
            StandardRobotRequest(
                kind=kind,
                command_id=command_id,
                site=canonical_site,
                program_version=self.program_version,
                point_set_version=self.point_set_version,
                payload_profile=payload_profile,
                source_boot_id=source_boot_id,
                monotonic_sequence=sequence,
                material_context={
                    "simulation_fixture_id": normalized_fixture,
                    "workflow_identity": dict(workflow_identity),
                },
                source="unilabos-simulation-node-job",
                backend_id=self.backend.backend_id,
                hardware_profile_ref=str(self.backend.hardware_profile_ref),
                hardware_profile_digest=str(self.backend.hardware_profile_digest),
                execution_environment=(
                    self.backend.capabilities.execution_environment
                ),
            )
        )

    def execute(self, request: StandardRobotRequest) -> dict[str, Any]:
        with self._motion_lock:
            return self._execute_locked(request)

    def _execute_locked(self, request: StandardRobotRequest) -> dict[str, Any]:
        existing = self.journal.get(request.command_id)
        if existing is not None:
            if not self._request_matches_current_backend(existing.request):
                return _public_rejection(
                    request.command_id,
                    self.boot_id,
                    "command_id 属于不同 RobotExecutionBackend/HardwareProfile，禁止跨 profile 重放",
                )
            if existing.request_hash != request.fingerprint():
                return _public_rejection(request.command_id, self.boot_id, "command_id 已被不同请求占用")
            return existing.public_result()
        if self.journal.has_unresolved():
            return _public_rejection(
                request.command_id,
                self.boot_id,
                "存在未完成 ACCEPTED/RUNNING/UNKNOWN 命令，禁止新运动",
            )

        try:
            created, record = self.journal.accept(request, self.boot_id)
        except (
            CommandConflictError,
            CommandSequenceError,
            CommandUnresolvedError,
            ValueError,
            TypeError,
        ) as exc:
            return _public_rejection(request.command_id, self.boot_id, str(exc))
        if not created:
            return record.public_result()

        try:
            self._validate_request(request)
            material = request.material_context.get("resource")
            fixture_id = request.material_context.get("simulation_fixture_id")
            if fixture_id is not None:
                if self.backend.capabilities.execution_environment != "simulation":
                    raise BackendRejectedError(
                        "physical HardwareProfile 禁止使用 simulation fixture"
                    )
                material_id = f"simulation-fixture:{str(fixture_id)}"
            else:
                material_id = _resource_reference(material, field_name="resource")
            resolved = self.resolver.resolve(
                operation=request.kind,
                command_id=request.command_id,
                target_site=request.site,
                material_id=material_id,
                program_version=request.program_version,
                point_set_version=request.point_set_version,
                payload_profile=request.payload_profile,
            )
            if resolved.backend_id != self.backend.backend_id:
                raise RuntimeError(
                    "SiteActionResolver 与 RobotExecutionBackend backend_id 不一致"
                )
            if resolved.backend_generation != self.backend.backend_generation:
                raise RuntimeError(
                    "SiteActionResolver 与 RobotExecutionBackend generation 不一致"
                )
        except Exception as exc:
            return self.journal.update(
                request.command_id,
                CommandState.REJECTED,
                self.boot_id,
                str(exc),
            ).public_result()

        try:
            resolved_output = {"resolved_site_action": resolved.to_dict()}
            self.journal.update(
                request.command_id,
                CommandState.RUNNING,
                self.boot_id,
                f"命令即将通过 {resolved.backend_id} 唯一派发",
                resolved_output,
            )
        except Exception as exc:
            return self.journal.update(
                request.command_id,
                CommandState.FAILED,
                self.boot_id,
                f"派发前无法冻结 ResolvedSiteAction: {exc}",
            ).public_result()
        try:
            receipt = self.backend.submit(resolved.command)
        except BackendRejectedError as exc:
            return self.journal.update(
                request.command_id,
                CommandState.FAILED,
                self.boot_id,
                str(exc),
                resolved_output,
            ).public_result()
        except Exception as exc:  # dispatch may have happened
            return self.journal.update(
                request.command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                f"{resolved.backend_id} 派发后结果不确定: {exc}",
                resolved_output,
            ).public_result()

        try:
            output = {
                **resolved_output,
                "dispatch_receipt": receipt.to_dict(),
            }
            # Persist the receipt before observation. If this or any later step
            # fails, RUNNING itself is an unresolved fence and prevents resend.
            self.journal.update(
                request.command_id,
                CommandState.RUNNING,
                self.boot_id,
                f"{resolved.backend_id} 已返回派发 receipt，正在独立观察与见证",
                output,
            )
            execution = self.backend.observe(resolved.command, receipt)
            completion = self.completion_verifier.verify(resolved, execution)
            output["execution_observation"] = {
                "state": execution.state.value,
                "message": execution.message,
                "evidence": dict(execution.evidence),
            }
            output["completion_observation"] = {
                "state": completion.state.value,
                "message": completion.message,
                "witnesses": dict(completion.witnesses),
            }
            state = _command_state_from_observation(completion.state)
            return self.journal.update(
                request.command_id,
                state,
                self.boot_id,
                completion.message,
                output,
            ).public_result()
        except Exception as exc:
            return self.journal.update(
                request.command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                f"派发后的观察/见证失败，结果不确定: {exc}",
                locals().get("output", resolved_output),
            ).public_result()

    def get_command(self, command_id: str) -> dict[str, Any]:
        record = self.journal.get(command_id)
        if record is None:
            return _public_rejection(command_id, self.boot_id, "命令不存在")
        return record.public_result()

    def reconcile(self, command_id: str) -> dict[str, Any]:
        record = self.journal.get(command_id)
        if record is None:
            return _public_rejection(command_id, self.boot_id, "命令不存在")
        if record.state is not CommandState.UNKNOWN:
            return record.public_result()

        raw_resolved = record.output.get("resolved_site_action")
        raw_receipt = record.output.get("dispatch_receipt")
        if not isinstance(raw_resolved, Mapping):
            return record.public_result()
        try:
            resolved = ResolvedSiteAction.from_dict(raw_resolved)
            receipt = (
                DispatchReceipt.from_dict(raw_receipt)
                if isinstance(raw_receipt, Mapping)
                else None
            )
        except (KeyError, TypeError, ValueError):
            return record.public_result()
        current_profile_digest = str(
            getattr(self.backend, "hardware_profile_digest", "")
        )
        if (
            resolved.backend_id != self.backend.backend_id
            or resolved.backend_generation != self.backend.backend_generation
            or resolved.hardware_profile_digest != current_profile_digest
        ):
            return self.journal.update(
                command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                "命令冻结的 Adapter generation/HardwareProfile 与当前 composition 不一致；禁止跨实例、跨环境对账",
                record.output,
            ).public_result()
        try:
            execution = self.backend.reconcile(resolved.command, receipt)
            completion = self.completion_verifier.verify(resolved, execution)
        except Exception as exc:
            return self.journal.update(
                command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                f"对账 Adapter 异常，继续保持 UNKNOWN: {exc}",
                record.output,
            ).public_result()
        state = _command_state_from_observation(completion.state)
        return self.journal.update(
            command_id,
            state,
            self.boot_id,
            (
                f"对账成功: {completion.message}"
                if state is CommandState.SUCCEEDED
                else completion.message
            ),
            {
                **record.output,
                "execution_observation": {
                    "state": execution.state.value,
                    "message": execution.message,
                    "evidence": dict(execution.evidence),
                },
                "completion_observation": {
                    "state": completion.state.value,
                    "message": completion.message,
                    "witnesses": dict(completion.witnesses),
                },
            },
        ).public_result()

    def _validate_request(self, request: StandardRobotRequest) -> None:
        if not self.actions_enabled:
            raise RuntimeError("标准 pick/place 尚未启用；必须先完成现场许可与见证映射验收")
        if request.program_version != self.program_version:
            raise ValueError(
                f"程序版本不匹配: 请求 {request.program_version}, 已部署 {self.program_version}"
            )
        if request.point_set_version != self.point_set_version:
            raise ValueError(
                f"点位集版本不匹配: 请求 {request.point_set_version}, 已部署 {self.point_set_version}"
            )
        if request.payload_profile not in self.payload_profiles:
            raise ValueError(f"负载配置不在允许列表: {request.payload_profile}")
        if not self._request_matches_current_backend(request.to_dict()):
            raise ValueError(
                "请求冻结的 RobotExecutionBackend/HardwareProfile 与当前 composition 不一致"
            )

    def _request_matches_current_backend(
        self,
        request: Mapping[str, Any],
    ) -> bool:
        return (
            str(request.get("backend_id") or "") == self.backend.backend_id
            and str(request.get("hardware_profile_ref") or "")
            == str(self.backend.hardware_profile_ref)
            and str(request.get("hardware_profile_digest") or "")
            == str(self.backend.hardware_profile_digest)
            and str(request.get("execution_environment") or "")
            == self.backend.capabilities.execution_environment
        )


def _record_from_row(row: sqlite3.Row) -> CommandRecord:
    return CommandRecord(
        request_hash=str(row["request_hash"]),
        request=json.loads(row["request_json"]),
        state=CommandState(str(row["state"])),
        boot_id=str(row["boot_id"]),
        message=str(row["message"]),
        output=json.loads(row["output_json"]),
    )


def _public_rejection(command_id: str, boot_id: str, message: str) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "state": CommandState.REJECTED.value,
        "success": False,
        "message": message,
        "boot_id": boot_id,
        "execution_environment": "unknown",
        "inventory_commit_allowed": False,
    }


def _plc_program_arguments(binding: SiteControlBinding) -> dict[str, Any]:
    """Resolve one legacy Site binding into vendor-neutral program arguments."""

    station = binding.station
    if station in {"S02", "S04", "S10"}:
        return {"position": binding.controller_position}
    if station in {"S03", "S11"}:
        return {
            "product_type": binding.product_type,
            "position": binding.sensor_key,
        }
    if station == "S072":
        return {
            "product_type": binding.product_type,
            "position": binding.controller_position,
        }
    if station == "S071":
        return {"position": binding.sensor_key}
    if station in {"S05", "S06"}:
        return {}
    raise ValueError(
        f"标准机械臂 Site 尚未绑定动作: {canonical_site_reference(binding)}"
    )


def _command_state_from_observation(state: ObservationState) -> CommandState:
    if state is ObservationState.SUCCEEDED:
        return CommandState.SUCCEEDED
    if state is ObservationState.FAILED:
        return CommandState.FAILED
    return CommandState.UNKNOWN


def _payload_profile_for_site(binding: SiteControlBinding) -> str:
    if binding.station == "S02":
        return "tip_box@v1"
    if binding.station in {"S03", "S11"}:
        return "beaker_500ml@v1" if binding.product_type == 1 else "sample_vial_500ml@v1"
    if binding.station == "S072" and binding.site_label.startswith("P"):
        return "powder_container@v1"
    if binding.station in {"S04", "S05", "S06", "S072"}:
        return "beaker_500ml@v1"
    if binding.station == "S071":
        return "powder_container@v1"
    if binding.station == "S10":
        return "liquid_reagent_bottle_100ml@v1"
    raise ValueError(f"Site 没有负载配置: {canonical_site_reference(binding)}")


def _payload_profile_for_resource(resource: Any) -> str:
    discriminators: list[str] = []

    def add(value: Any) -> None:
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in discriminators:
            discriminators.append(normalized)

    if isinstance(resource, Mapping):
        for key in ("category", "class", "klass", "type"):
            add(resource.get(key))
        extra = resource.get("unilabos_extra") or resource.get("extra")
    else:
        for attribute in ("category", "klass", "type"):
            add(getattr(resource, attribute, None))
        extra = getattr(resource, "unilabos_extra", None) or getattr(resource, "extra", None)

    if isinstance(extra, Mapping):
        for key in ("unilabos_resource_class", "class", "klass", "category"):
            add(extra.get(key))

    identity = " ".join(discriminators)
    if "beaker_500ml" in identity or "szlab_beaker_500ml" in identity or "beaker" in discriminators:
        return "beaker_500ml@v1"
    if "sample_vial_500ml" in identity or "sample_vial" in discriminators:
        max_volume = getattr(resource, "max_volume", None)
        if max_volume not in (None, 500_000, 500_000.0):
            raise ValueError("当前标准 Site 仅支持 500 mL 样品瓶")
        return "sample_vial_500ml@v1"
    if "liquid_reagent_bottle_100ml" in identity or "liquid_reagent" in discriminators:
        return "liquid_reagent_bottle_100ml@v1"
    if "powder_container" in identity or "powder_reagent" in discriminators:
        return "powder_container@v1"
    if "szlab_tip_box" in identity or "tip_box" in discriminators:
        return "tip_box@v1"
    if any(value in {"tip", "pipette_tip"} for value in discriminators):
        return "pipette_tip@v1"
    category = discriminators[0] if discriminators else "-"
    raise ValueError(f"无法从 ResourceSlot 推断机械臂负载配置: category={category}")


def _resource_reference(resource: Any, *, field_name: str) -> str:
    if isinstance(resource, Mapping):
        for key in ("unilabos_uuid", "uuid", "id", "name"):
            value = resource.get(key)
            if value:
                return str(value)
    else:
        for attribute in ("unilabos_uuid", "uuid", "id", "name"):
            value = getattr(resource, attribute, None)
            if value:
                return str(value)
    raise ValueError(f"{field_name} 缺少稳定资源标识")


def _capture_workflow_execution_identity() -> Mapping[str, str]:
    """兼容导入；旧 OS 没有 execution identity 时由调用方 fail-closed。"""

    try:
        from unilabos.observability.runtime import (
            capture_workflow_execution_identity,
        )
    except ImportError:
        return {}
    return capture_workflow_execution_identity()


def _workflow_node_command_id(identity: Mapping[str, str]) -> str:
    """使用 OS 已认证的 WorkflowNodeJob UUID，不接受业务侧幂等参数。"""

    if not isinstance(identity, Mapping):
        raise TypeError("Workflow execution identity 必须是对象")
    raw_job_uuid = str(identity.get("node_job_uuid") or "").strip()
    try:
        job_uuid = str(UUID(raw_job_uuid))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(
            "缺少有效 WorkflowNodeJob execution identity；标准机械臂动作不接受业务侧幂等标识"
        ) from exc
    return f"workflow-node-job:{job_uuid}"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    for attribute in ("unilabos_uuid", "uuid", "id"):
        candidate = getattr(value, attribute, None)
        if candidate:
            return {attribute: str(candidate)}
    return str(value)
