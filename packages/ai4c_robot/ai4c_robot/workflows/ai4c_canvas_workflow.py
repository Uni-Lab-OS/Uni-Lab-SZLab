"""AI4C local UI 的完整搬运调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

AI4C_robot_arm = device("AI4C_robot_arm")


@workflow_definition(
    workflow_id="szlab_canvas_workflow",
    revision="python-v1",
    parameter_ui={
        "loading_position": {"title": "上料架位置", "description": "范围 1-8。"},
        "unloading_position": {"title": "下料架位置", "description": "范围 1-8。"},
    },
)
def szlab_canvas_workflow(
    loading_position: int = 1,
    unloading_position: int = 1,
) -> None:
    AI4C_robot_arm.pick_well_plate_from_loading_rack(position=loading_position)
    AI4C_robot_arm.place_well_plate_to_pipetting_station()
    AI4C_robot_arm.pick_well_plate_from_pipetting_station()
    AI4C_robot_arm.place_well_plate_to_magnetic_stirrer()
    AI4C_robot_arm.pick_well_plate_from_magnetic_stirrer()
    AI4C_robot_arm.place_well_plate_to_hplc_station()
    AI4C_robot_arm.pick_well_plate_from_hplc_station()
    AI4C_robot_arm.place_well_plate_to_unloading_rack(position=unloading_position)
