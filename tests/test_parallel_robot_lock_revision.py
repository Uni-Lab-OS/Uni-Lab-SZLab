import json
from pathlib import Path


REVISION_PATH = (
    Path(__file__).parents[1]
    / "szlab_poly_studio"
    / "workflows"
    / "szlab_parallel_robot_lock.revision.json"
)


def test_parallel_robot_branches_merge_directly_at_final_stir() -> None:
    revision = json.loads(REVISION_PATH.read_text(encoding="utf-8"))

    invocations = revision["invocations"]
    node_ids = {invocation["node_id"] for invocation in invocations}
    edges = revision["control_edges"]

    assert revision["revision_id"] == "szlab-parallel-robot-lock-rev-2"
    assert node_ids == {
        "s05_photo",
        "s06_addition",
        "robot_pour_type_1",
        "robot_pour_type_2",
        "final_stir",
    }
    assert all(invocation["action_ref"] != "os_control.join" for invocation in invocations)
    assert {
        edge["source"] for edge in edges if edge["target"] == "final_stir"
    } == {"robot_pour_type_1", "robot_pour_type_2"}
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in edges)
    assert set(revision["layout"]["nodes"]) == node_ids
