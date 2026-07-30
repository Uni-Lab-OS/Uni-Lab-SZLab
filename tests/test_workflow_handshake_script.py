from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "szlab_workflow_handshake.py"
SPEC = importlib.util.spec_from_file_location("szlab_workflow_handshake", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
handshake = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handshake
SPEC.loader.exec_module(handshake)


class MemoryAdapter:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {
            handshake.ROBOT_TASK_NUMBER: 0,
            handshake.S04_ROBOT_POSITION: 0,
            handshake.S06_PROCESS: 0,
            handshake.S06_PARAMS_WRITTEN: False,
            handshake.s04_process(1): 0,
            handshake.s04_params_written(1): False,
        }

    def read(self, name: str) -> Any:
        return self.values[name]

    def write(self, name: str, value: Any) -> None:
        self.values[name] = value


def test_catalog_lists_all_workflows_and_five_supported_actions() -> None:
    specs = handshake.build_workflow_specs()

    assert len(specs) == 12
    assert len(handshake.SUPPORTED_ACTIONS) == 5
    assert {item.workflow_id for item in specs} == {
        "szlab_magnetic_stirring_workflow",
        "szlab_photoshotting_workflow",
        "szlab_robot_action_workflow",
        "s04_robot_stirring_workflow",
        "s06_robot_workflow",
        "s07_robot_workflow",
        "szlab_s07_solid_addition_workflow",
        "s08_cap_workflow",
        "szlab_s09_pipetting_workflow",
        "szlab_stack_s05_s06_workflow",
        "szlab_mixer_workflow",
        "szlab_mixer_pump_production",
    }


def test_s04_three_action_handshake_changes_sensor_and_resets() -> None:
    adapter = MemoryAdapter()
    simulator = handshake.WorkflowHandshakeSimulator(
        adapter,
        position=1,
        process_delay=1.0,
    )
    simulator.initialize()

    adapter.write(handshake.ROBOT_TASK_NUMBER, 7)
    adapter.write(handshake.S04_ROBOT_POSITION, 1)
    adapter.write(handshake.ROBOT_WRITE_DONE, True)
    events = simulator.step(now=0.0)
    assert [(event.action, event.phase) for event in events] == [
        (handshake.SUPPORTED_ACTIONS[0], "accepted")
    ]
    assert adapter.read(handshake.ROBOT_WRITE_ALLOWED) is False

    events = simulator.step(now=1.0)
    assert [(event.action, event.phase) for event in events] == [
        (handshake.SUPPORTED_ACTIONS[0], "completed")
    ]
    assert adapter.read(handshake.s04_sensor(1)) is True
    assert adapter.read(handshake.ROBOT_TASK_COMPLETE) == 7

    adapter.write(handshake.ROBOT_WRITE_DONE, False)
    adapter.write(handshake.ROBOT_TASK_NUMBER, 0)
    simulator.step(now=1.1)
    assert adapter.read(handshake.ROBOT_TASK_COMPLETE) == 0
    assert adapter.read(handshake.ROBOT_WRITE_ALLOWED) is True

    adapter.write(handshake.s04_process(1), 3)
    adapter.write(handshake.s04_params_written(1), True)
    events = simulator.step(now=2.0)
    assert [(event.action, event.phase) for event in events] == [
        (handshake.SUPPORTED_ACTIONS[1], "accepted")
    ]
    events = simulator.step(now=3.0)
    assert [(event.action, event.phase) for event in events] == [
        (handshake.SUPPORTED_ACTIONS[1], "completed")
    ]
    assert adapter.read(handshake.s04_done(1)) is True

    adapter.write(handshake.s04_params_written(1), False)
    adapter.write(handshake.s04_process(1), 0)
    simulator.step(now=3.1)
    assert adapter.read(handshake.s04_done(1)) is False
    assert adapter.read(handshake.s04_allow(1)) is True

    adapter.write(handshake.ROBOT_TASK_NUMBER, 8)
    adapter.write(handshake.S04_ROBOT_POSITION, 1)
    adapter.write(handshake.ROBOT_WRITE_DONE, True)
    simulator.step(now=4.0)
    events = simulator.step(now=5.0)
    assert [(event.action, event.phase) for event in events] == [
        (handshake.SUPPORTED_ACTIONS[2], "completed")
    ]
    assert adapter.read(handshake.s04_sensor(1)) is False
    assert simulator.completed_actions == 3


def test_s06_handshake_produces_fresh_done_cycle() -> None:
    adapter = MemoryAdapter()
    simulator = handshake.WorkflowHandshakeSimulator(
        adapter,
        pump=1,
        process_delay=0.5,
    )
    simulator.initialize()
    adapter.write(handshake.S06_PROCESS, 1)
    adapter.write(handshake.S06_PARAMS_WRITTEN, True)

    accepted = simulator.step(now=10.0)
    completed = simulator.step(now=10.5)

    assert [(event.action, event.phase) for event in accepted] == [
        (handshake.SUPPORTED_ACTIONS[4], "accepted")
    ]
    assert [(event.action, event.phase) for event in completed] == [
        (handshake.SUPPORTED_ACTIONS[4], "completed")
    ]
    assert adapter.read(handshake.S06_DONE) is True

    adapter.write(handshake.S06_PROCESS, 0)
    adapter.write(handshake.S06_PARAMS_WRITTEN, False)
    reset = simulator.step(now=10.6)
    assert [(event.action, event.phase) for event in reset] == [
        (handshake.SUPPORTED_ACTIONS[4], "reset")
    ]
    assert adapter.read(handshake.S06_DONE) is False
    assert adapter.read(handshake.S06_ALLOW) is True


def test_cleanup_only_resets_simulator_owned_outputs() -> None:
    adapter = MemoryAdapter()
    simulator = handshake.WorkflowHandshakeSimulator(adapter)
    simulator.initialize()
    adapter.write(handshake.ROBOT_TASK_NUMBER, 7)

    simulator.cleanup()

    assert adapter.read(handshake.ROBOT_HOME) is False
    assert adapter.read(handshake.ROBOT_WRITE_ALLOWED) is False
    assert adapter.read(handshake.s04_sensor(1)) is False
    assert adapter.read(handshake.S05_RESULT) == 0
    assert adapter.read(handshake.S06_BEAKER_SENSOR) is False
    assert adapter.read(handshake.S06_STORAGE_BOTTLE_SENSOR[1]) is False
    assert adapter.read(handshake.ROBOT_TASK_NUMBER) == 7
