"""SZLab 长动作的有界阶段反馈工具。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from unilabos.ros.action_feedback import publish_action_feedback


def wait_with_action_feedback(
    *,
    variable: str,
    expected: Any,
    phase: str,
    position: int,
    timeout: float,
    read: Callable[[], Any],
    wait: Callable[[], bool],
    poll: bool,
    interval: float = 1.0,
    precondition: str | None = None,
) -> tuple[bool, Any, float]:
    """等待条件并在值变化或心跳到期时发布结构化反馈。"""

    started_at = time.monotonic()
    last_actual: Any = None

    def report(outcome: str, *, force: bool = False) -> None:
        elapsed = max(0.0, time.monotonic() - started_at)
        publish_action_feedback(
            phase,
            {
                "position": position,
                "sensor": variable,
                "precondition": precondition,
                "expected_value": expected,
                "actual_value": last_actual,
                "elapsed_s": round(elapsed, 3),
                "timeout_s": float(timeout),
                "remaining_s": round(max(0.0, timeout - elapsed), 3),
                "outcome": outcome,
            },
            force=force,
            heartbeat_interval_s=5.0,
        )

    if not poll:
        try:
            last_actual = read()
        except Exception:
            last_actual = None
        report("waiting", force=True)
        success = wait()
        if success:
            last_actual = expected
        else:
            try:
                last_actual = read()
            except Exception:
                pass
        report("satisfied" if success else "timeout", force=True)
        return success, last_actual, max(0.0, time.monotonic() - started_at)

    report("waiting", force=True)
    while time.monotonic() - started_at <= timeout:
        try:
            last_actual = read()
        except Exception:
            last_actual = None
        if last_actual == expected:
            report("satisfied", force=True)
            return True, last_actual, max(0.0, time.monotonic() - started_at)
        report("waiting")
        time.sleep(interval)
    report("timeout", force=True)
    return False, last_actual, max(0.0, time.monotonic() - started_at)


def publish_action_phase(
    phase: str,
    position: int,
    outcome: str,
    **details: Any,
) -> None:
    """发布 S04 阶段快照，统一位置与结果字段。"""

    publish_action_feedback(
        phase,
        {"position": position, "outcome": outcome, **details},
        force=True,
    )


def publish_completion_phase(
    *,
    position: int,
    sensor: str,
    timeout: float,
    elapsed: float,
    outcome: str,
    actual: Any,
) -> None:
    """发布 S04 完成信号等待快照。"""

    publish_action_phase(
        "waiting_completion",
        position,
        outcome,
        sensor=sensor,
        expected_value=True,
        actual_value=actual,
        elapsed_s=round(elapsed, 3),
        timeout_s=float(timeout),
        remaining_s=round(max(0.0, timeout - elapsed), 3),
    )


__all__ = [
    "publish_action_phase",
    "publish_completion_phase",
    "wait_with_action_feedback",
]
