"""S04 磁搅作业阶段反馈回归。"""

from __future__ import annotations

from typing import Any

from unilabos.ros.action_feedback import attach_action_feedback

from szlab_poly_studio.common.action_phase_feedback import wait_with_action_feedback
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)


class FeedbackGateway:
    def __init__(self, *, material_ready: bool = True) -> None:
        self.material_ready = material_ready
        self.values: dict[str, Any] = {}

    def read_variable(self, name: str, use_cache: bool = False) -> Any:
        del use_cache
        if "传感器状态" in name:
            return self.material_ready
        return self.values.get(name, False)

    def write_variable(self, name: str, value: Any) -> bool:
        self.values[name] = value
        return True

    def wait_equal(
        self,
        name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        del timeout, interval
        if "传感器状态" in name:
            return self.material_ready is expected
        return True

    wait_variable_equal = wait_equal

    def wait_variable_true(
        self,
        name: str,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        return self.wait_equal(name, True, timeout=timeout, interval=interval)

    def wait_new_cycle_done(
        self,
        name: str,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        del name, timeout, interval
        return True


def _run(*, material_ready: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    feedback: list[dict[str, Any]] = []
    device = SzlabMixerMagneticStirrerDevice(
        plc_gateway=FeedbackGateway(material_ready=material_ready),
        timeout=0.01,
    )
    with attach_action_feedback(
        lambda payload: feedback.append(payload) is None,
        job_uuid="job-s04",
        task_uuid="task-s04",
        device_id="szlab_mixer_stirrer",
        action_name="run_stirring",
    ):
        result = device.run_stirring(position=2, duration=0)
    return result, feedback


def test_success_reports_all_execution_phases_with_monotonic_sequences() -> None:
    result, feedback = _run(material_ready=True)

    assert result["success"] is True
    phases = [item["phase"] for item in feedback]
    assert phases[0:2] == ["waiting_precondition", "waiting_precondition"]
    assert phases[-5:] == [
        "writing_parameters",
        "processing",
        "waiting_completion",
        "waiting_completion",
        "terminal",
    ]
    assert [item["feedback_sequence"] for item in feedback] == list(range(1, len(feedback) + 1))
    assert all(item["job_uuid"] == "job-s04" for item in feedback)
    assert [item["diagnostic_event"] for item in feedback[:2]] == [
        "precondition_check_started",
        "satisfied",
    ]


def test_material_timeout_terminal_retains_last_sensor_observation() -> None:
    result, feedback = _run(material_ready=False)

    assert result["success"] is False
    terminal = feedback[-1]
    assert terminal["phase"] == "terminal"
    assert terminal["outcome"] == "timeout"
    assert terminal["position"] == 2
    assert terminal["sensor"] == "传感器状态_上位机[2].NO[11]"
    assert terminal["expected_value"] is True
    assert terminal["actual_value"] is False
    assert terminal["elapsed_s"] >= 0
    assert terminal["timeout_s"] == 0.01
    assert terminal["remaining_s"] == 0.0
    precondition_events = [
        item["diagnostic_event"]
        for item in feedback
        if item["phase"] == "waiting_precondition"
    ]
    assert precondition_events[0] == "precondition_check_started"
    assert precondition_events[-1] == "timed_out"


def test_polled_gateway_reports_started_waiting_and_timed_out() -> None:
    feedback: list[dict[str, Any]] = []
    with attach_action_feedback(
        lambda payload: feedback.append(payload) is None,
        job_uuid="job-poll",
        task_uuid="task-poll",
        device_id="szlab_mixer_stirrer",
        action_name="run_stirring",
    ):
        result = wait_with_action_feedback(
            variable="传感器状态_上位机[2].NO[10]",
            expected=True,
            phase="waiting_precondition",
            position=1,
            timeout=0.0,
            read=lambda: False,
            wait=lambda: False,
            poll=True,
            interval=0.0,
            precondition="material_present",
        )

    assert result[0] is False
    assert [item["diagnostic_event"] for item in feedback] == [
        "precondition_check_started",
        "waiting",
        "timed_out",
    ]
