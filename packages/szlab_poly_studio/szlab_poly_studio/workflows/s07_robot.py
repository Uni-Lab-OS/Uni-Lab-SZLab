"""legacy s07_robot_workflow.json 的等价 Python 表达。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_mixer_robot = device("szlab_mixer_robot")


@workflow_definition(
    workflow_id="s07_robot_workflow",
    revision="python-v1",
)
def s07_robot_workflow() -> None:
    szlab_mixer_robot.submit_place_to_s071(position="1-1")
    szlab_mixer_robot.submit_place_to_s072(product_type=1, position=1)
    szlab_mixer_robot.submit_pick_from_s072(product_type=1, position=1)
