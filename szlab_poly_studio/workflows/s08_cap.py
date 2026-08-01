"""legacy s08_open_close_workflow.json 的等价 Python 表达。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_s08_cap_station = device("szlab_s08_cap_station")


@workflow_definition(
    workflow_id="s08_cap_workflow",
    revision="python-v1",
)
def s08_cap_workflow() -> None:
    szlab_s08_cap_station.process_cap_with_sample_parts(
        operation="open",
        vial_type="liquid_100ml",
        sample_id_1=101,
        sample_id_2=102,
        sample_id_3=103,
        timeout=300.0,
    )
    szlab_s08_cap_station.process_cap_with_sample_parts(
        operation="close",
        vial_type="liquid_100ml",
        sample_id_1=101,
        sample_id_2=102,
        sample_id_3=103,
        timeout=300.0,
    )
