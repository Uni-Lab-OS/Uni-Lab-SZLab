from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from szlab_poly_studio.common.site_control_bindings import (
    SiteControlBinding,
    canonical_site_reference,
    resolve_canonical_site_reference,
    resolve_robot_site_reference,
)
from szlab_poly_studio.devices.szlab_mixer_robot.robot_tasks import (
    ROBOT_HOME_VARIABLE,
    ROBOT_WRITE_ALLOWED_VARIABLE,
    build_variables,
)

TOOL_PAYLOAD_SENSOR_VARIABLE = "传感器状态_上位机[3].NO[6]"
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

    def __post_init__(self) -> None:
        required = {
            "command_id": self.command_id,
            "site": self.site,
            "program_version": self.program_version,
            "point_set_version": self.point_set_version,
            "payload_profile": self.payload_profile,
            "source_boot_id": self.source_boot_id,
        }
        missing = [name for name, value in required.items() if not isinstance(value, str) or not value.strip()]
        if missing:
            raise ValueError(f"标准机械臂请求缺少字段: {', '.join(missing)}")
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
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RobotCommand:
    """传给 PLC/厂家 adapter 的完整标准化命令；不包含业务 SkillBinding。"""

    kind: Literal["pick", "place"]
    command_id: str
    skill_id: str
    station: str
    site: str
    controller_position: int
    presence_variable: str
    payload_profile: str
    legacy_runner_name: str
    legacy_parameters: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "command_id": self.command_id,
            "skill_id": self.skill_id,
            "station": self.station,
            "site": self.site,
            "controller_position": self.controller_position,
            "presence_variable": self.presence_variable,
            "payload_profile": self.payload_profile,
            "legacy_runner_name": self.legacy_runner_name,
            "legacy_parameters": dict(self.legacy_parameters),
        }


@dataclass(frozen=True)
class CommandRecord:
    request_hash: str
    request: Mapping[str, Any]
    state: CommandState
    boot_id: str
    message: str
    output: Mapping[str, Any]

    def public_result(self) -> dict[str, Any]:
        return {
            "command_id": str(self.request["command_id"]),
            "state": self.state.value,
            "success": self.state is CommandState.SUCCEEDED,
            "message": self.message,
            "boot_id": self.boot_id,
        }


class CommandConflictError(RuntimeError):
    pass


class CommandSequenceError(RuntimeError):
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

    def has_unknown(self) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM szlab_robot_commands_v1 WHERE state = ? LIMIT 1",
                (CommandState.UNKNOWN.value,),
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


class SZLabLegacyPLCAdapter:
    """只消费 RobotCommand 的 SZLab PLC adapter；Legacy action 本身保持不变。"""

    def __init__(self, owner: Any):
        self.owner = owner

    def execute(self, command: RobotCommand) -> Mapping[str, Any]:
        if command.station == "S071":
            return self._execute_s071(command)

        runner = getattr(self.owner, command.legacy_runner_name, None)
        if not callable(runner):
            raise ValueError(f"标准命令没有 Legacy PLC runner: {command.legacy_runner_name}")
        inspect.signature(runner).bind(**dict(command.legacy_parameters))
        result = runner(**dict(command.legacy_parameters))
        if not isinstance(result, Mapping):
            return result
        witness_key = "source_sensor_variable" if command.kind == "pick" else "target_sensor_variable"
        if witness_key in result or not command.presence_variable:
            return result
        return {**result, witness_key: command.presence_variable}

    def _execute_s071(self, command: RobotCommand) -> Mapping[str, Any]:
        """标准路径按 2×3 紧凑编号下发；不改变 Legacy `_slot_number`。"""

        is_pick = command.kind == "pick"
        sensor = command.presence_variable
        return self.owner._submit_robot_task(
            task=command.kind,
            station="S071",
            task_number=14 if is_pick else 13,
            variables=build_variables(
                "pick_from_s071" if is_pick else "place_to_s071",
                S071取放料编号=command.controller_position,
            ),
            reset_variables={"S071取放料编号": 0, "任务号": 0},
            precheck=lambda: self.owner._ensure_sensor_gate(
                sensor,
                is_pick,
                "S071 取粉罐源位必须有粉罐" if is_pick else "S071 放粉罐目标位必须为空",
            ),
            position=command.site.rsplit("/", maxsplit=1)[-1],
            controller_position=command.controller_position,
            **({"source_sensor_variable": sensor} if is_pick else {"target_sensor_variable": sensor}),
        )


class SZLabStandardRobotGateway:
    """Standard pick/place façade over the unchanged SZLab PLC handshake."""

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
    ):
        self.owner = owner
        self.program_version = program_version
        self.point_set_version = point_set_version
        self.payload_profiles = frozenset(payload_profiles)
        self.actions_enabled = bool(actions_enabled)
        self.permit_asserts_remote_auto = bool(permit_asserts_remote_auto)
        self.permit_asserts_safety_normal = bool(permit_asserts_safety_normal)
        self.motion_permit_variable = motion_permit_variable
        self.tool_payload_sensor_variable = tool_payload_sensor_variable
        self.boot_id = str(uuid4())
        self._motion_lock = threading.RLock()
        self._sequence = time.monotonic_ns()
        self.journal = SZLabRobotCommandJournal(journal_path)
        self.adapter = SZLabLegacyPLCAdapter(owner)
        self.journal.mark_previous_boot_inflight_unknown(self.boot_id)

    def execute_site(
        self,
        *,
        kind: Literal["pick", "place"],
        resource: Any,
        warehouse: Any,
        site: str,
        transfer_id: str,
    ) -> dict[str, Any]:
        """由最小工作流参数生成稳定、可重放的标准请求。"""

        transfer_id = str(transfer_id).strip()
        if not transfer_id:
            return _public_rejection("", self.boot_id, "transfer_id 不能为空")
        try:
            binding = resolve_robot_site_reference(warehouse, site)
            canonical_site = canonical_site_reference(binding)
            payload_profile = _payload_profile_for_resource(resource)
            warehouse_reference = _resource_reference(warehouse, field_name="warehouse")
        except (TypeError, ValueError) as exc:
            return _public_rejection("", self.boot_id, str(exc))

        command_id = _site_command_id(transfer_id, kind, warehouse_reference, canonical_site)
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
            material_context={"resource": resource, "warehouse": warehouse},
            source="unilabos-standard-site-action",
        )
        return self.execute(request)

    def execute(self, request: StandardRobotRequest) -> dict[str, Any]:
        with self._motion_lock:
            return self._execute_locked(request)

    def _execute_locked(self, request: StandardRobotRequest) -> dict[str, Any]:
        existing = self.journal.get(request.command_id)
        if existing is not None:
            if existing.request_hash != request.fingerprint():
                return _public_rejection(request.command_id, self.boot_id, "command_id 已被不同请求占用")
            return existing.public_result()
        if self.journal.has_unknown():
            return _public_rejection(request.command_id, self.boot_id, "存在未对账 UNKNOWN 命令，禁止新运动")

        try:
            created, record = self.journal.accept(request, self.boot_id)
        except (CommandConflictError, CommandSequenceError, ValueError, TypeError) as exc:
            return _public_rejection(request.command_id, self.boot_id, str(exc))
        if not created:
            return record.public_result()

        try:
            command = self._validate_request(request)
        except (ValueError, TypeError, RuntimeError) as exc:
            return self.journal.update(
                request.command_id,
                CommandState.REJECTED,
                self.boot_id,
                str(exc),
            ).public_result()

        self.journal.update(
            request.command_id,
            CommandState.RUNNING,
            self.boot_id,
            "命令已下发到既有 SZLab PLC 握手驱动",
        )
        try:
            legacy_result = self.adapter.execute(command)
        except Exception as exc:  # communication may have failed after dispatch
            return self.journal.update(
                request.command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                f"PLC 派发后结果不确定: {exc}",
            ).public_result()

        if not isinstance(legacy_result, Mapping):
            return self.journal.update(
                request.command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                "旧驱动返回值不是对象，无法确认物理结果",
                {"legacy_result": _jsonable(legacy_result)},
            ).public_result()

        output = {
            "command": command.to_dict(),
            "legacy_result": _jsonable(legacy_result),
        }
        if not bool(legacy_result.get("success")):
            state = CommandState.REJECTED if legacy_result.get("status") == "rejected" else CommandState.UNKNOWN
            message = str(legacy_result.get("message") or "旧驱动未确认动作成功")
            return self.journal.update(request.command_id, state, self.boot_id, message, output).public_result()

        witness_ok, witness_message, witnesses = self._observe_completion(request.kind, legacy_result)
        output["witnesses"] = witnesses
        state = CommandState.SUCCEEDED if witness_ok else CommandState.UNKNOWN
        return self.journal.update(
            request.command_id,
            state,
            self.boot_id,
            witness_message,
            output,
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

        legacy_result = record.output.get("legacy_result")
        if not isinstance(legacy_result, Mapping):
            return record.public_result()
        kind = str(record.request.get("kind", ""))
        if kind not in {"pick", "place"}:
            return record.public_result()
        witness_ok, witness_message, witnesses = self._observe_completion(kind, legacy_result)
        if not witness_ok:
            return self.journal.update(
                command_id,
                CommandState.UNKNOWN,
                self.boot_id,
                witness_message,
                {**record.output, "witnesses": witnesses},
            ).public_result()
        return self.journal.update(
            command_id,
            CommandState.SUCCEEDED,
            self.boot_id,
            f"对账成功: {witness_message}",
            {**record.output, "witnesses": witnesses},
        ).public_result()

    def _validate_request(self, request: StandardRobotRequest):
        if not self.actions_enabled:
            raise RuntimeError("标准 pick/place 尚未启用；必须先完成现场许可与见证映射验收")
        if not self.permit_asserts_remote_auto:
            raise RuntimeError("未声明运动许可同时见证 REMOTE_AUTO，按 fail-closed 拒绝")
        if not self.permit_asserts_safety_normal:
            raise RuntimeError("未声明运动许可同时见证安全状态可运动，按 fail-closed 拒绝")
        if not self.motion_permit_variable:
            raise RuntimeError("未配置现有 PLC/机器人运动许可变量")
        if not bool(self.owner._read_variable(self.motion_permit_variable, use_cache=False)):
            raise RuntimeError(f"运动许可被拒绝: {self.motion_permit_variable}")
        if not bool(self.owner._read_variable(ROBOT_HOME_VARIABLE, use_cache=False)):
            raise RuntimeError("Robot_Home 未确认")
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

        command = _robot_command_from_request(request)

        tool_holding = bool(self.owner._read_variable(self.tool_payload_sensor_variable, use_cache=False))
        if request.kind == "pick" and tool_holding:
            raise RuntimeError("pick 前机械手夹爪已有物料")
        if request.kind == "place" and not tool_holding:
            raise RuntimeError("place 前机械手夹爪未见证持料")
        return command

    def _observe_completion(
        self,
        kind: Literal["pick", "place"] | str,
        legacy_result: Mapping[str, Any],
    ) -> tuple[bool, str, dict[str, Any]]:
        site_sensor_key = "source_sensor_variable" if kind == "pick" else "target_sensor_variable"
        site_sensor = str(legacy_result.get(site_sensor_key) or "")
        if not site_sensor:
            return False, f"{kind} 缺少工位物料见证变量", {}
        try:
            site_present = bool(self.owner._read_variable(site_sensor, use_cache=False))
            tool_holding = bool(self.owner._read_variable(self.tool_payload_sensor_variable, use_cache=False))
            robot_home = bool(self.owner._read_variable(ROBOT_HOME_VARIABLE, use_cache=False))
        except Exception as exc:
            return False, f"完成后见证读取失败: {exc}", {}

        expected_site = kind == "place"
        expected_tool = kind == "pick"
        witnesses = {
            "site_sensor": site_sensor,
            "site_present": site_present,
            "expected_site_present": expected_site,
            "tool_sensor": self.tool_payload_sensor_variable,
            "tool_holding": tool_holding,
            "expected_tool_holding": expected_tool,
            "robot_home": robot_home,
            "completion_value": _jsonable(legacy_result.get("completion_value")),
        }
        if site_present != expected_site or tool_holding != expected_tool or not robot_home:
            return False, f"{kind} 完成见证不一致，保持 UNKNOWN，禁止自动重发", witnesses
        return True, f"{kind} 已由 PLC 完成、工位在位、夹爪和 Robot_Home 共同见证", witnesses


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
    }


def _robot_command_from_request(request: StandardRobotRequest) -> RobotCommand:
    binding = resolve_canonical_site_reference(request.site)
    if not binding.robot_action_ready:
        raise ValueError(binding.blocked_reason or f"Site {request.site} 尚未启用标准机械臂动作")
    expected_payload = _payload_profile_for_site(binding)
    if request.payload_profile != expected_payload:
        raise ValueError(
            f"Site {canonical_site_reference(binding)} 要求负载 {expected_payload}, "
            f"实际为 {request.payload_profile}"
        )

    station = binding.station
    skill_station = station.lower()
    skill_id = f"pick_from_{skill_station}" if request.kind == "pick" else f"place_to_{skill_station}"
    legacy_runner_name = f"_run_{skill_station}_{request.kind}"
    legacy_parameters: dict[str, Any]
    if station in {"S02", "S04", "S10"}:
        legacy_parameters = {"position": binding.controller_position}
    elif station in {"S03", "S11"}:
        legacy_parameters = {
            "product_type": binding.product_type,
            "position": binding.sensor_key,
        }
    elif station == "S072":
        legacy_parameters = {
            "product_type": binding.product_type,
            "position": binding.controller_position,
        }
    elif station == "S071":
        legacy_parameters = {"position": binding.sensor_key}
    elif station in {"S05", "S06"}:
        legacy_parameters = {}
    else:
        raise ValueError(f"标准机械臂 Site 尚未绑定动作: {canonical_site_reference(binding)}")

    return RobotCommand(
        kind=request.kind,
        command_id=request.command_id,
        skill_id=skill_id,
        station=station,
        site=canonical_site_reference(binding),
        controller_position=binding.controller_position,
        presence_variable=binding.presence_variable,
        payload_profile=request.payload_profile,
        legacy_runner_name=legacy_runner_name,
        legacy_parameters=legacy_parameters,
    )


def _payload_profile_for_site(binding: SiteControlBinding) -> str:
    if binding.station == "S02":
        return "tip_box@v1"
    if binding.station in {"S03", "S11"}:
        return "beaker_500ml@v1" if binding.product_type == 1 else "sample_vial_500ml@v1"
    if binding.station in {"S04", "S05", "S06", "S072"}:
        return "beaker_500ml@v1"
    if binding.station == "S071":
        return "powder_container@v1"
    if binding.station == "S10":
        return "liquid_reagent_bottle_100ml@v1"
    raise ValueError(f"Site 没有负载配置: {canonical_site_reference(binding)}")


def _payload_profile_for_resource(resource: Any) -> str:
    category = str(getattr(resource, "category", "") or "").strip().lower()
    if not category and isinstance(resource, Mapping):
        category = str(resource.get("category") or resource.get("class") or "").strip().lower()
    if category == "beaker" or "beaker_500ml" in category:
        return "beaker_500ml@v1"
    if category == "sample_vial" or "sample_vial_500ml" in category:
        max_volume = getattr(resource, "max_volume", None)
        if max_volume not in (None, 500_000, 500_000.0):
            raise ValueError("当前标准 Site 仅支持 500 mL 样品瓶")
        return "sample_vial_500ml@v1"
    if category == "liquid_reagent" or "liquid_reagent_bottle_100ml" in category:
        return "liquid_reagent_bottle_100ml@v1"
    if category == "powder_reagent" or "powder_container" in category:
        return "powder_container@v1"
    if category == "tip_box" or "szlab_tip_box" in category:
        return "tip_box@v1"
    if category in {"tip", "pipette_tip"}:
        return "pipette_tip@v1"
    raise ValueError(f"无法从 ResourceSlot 推断机械臂负载配置: category={category or '-'}")


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


def _site_command_id(transfer_id: str, kind: str, warehouse: str, site: str) -> str:
    readable = f"{transfer_id}:{kind}:{warehouse}:{site}"
    if len(readable) <= 128:
        return readable
    digest = hashlib.sha256(readable.encode("utf-8")).hexdigest()
    return f"site-action:{digest}"


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
