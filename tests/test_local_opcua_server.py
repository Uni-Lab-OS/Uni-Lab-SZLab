from opcua import ua

from scripts.szlab_local_opcua_server import (
    DEFAULT_CSV,
    _variant_definition,
    load_variable_definitions,
)


def test_variant_definition_preserves_plc_scalar_types() -> None:
    assert _variant_definition("ready", "BOOL", "TRUE").value is True
    assert _variant_definition("ready", "BOOL", "TRUE").variant_type is ua.VariantType.Boolean
    assert _variant_definition("task", "DINT", "7").variant_type is ua.VariantType.Int32
    assert _variant_definition("mass", "REAL", "1.25").variant_type is ua.VariantType.Float
    assert _variant_definition("label", "STRING[80]", "powder").variant_type is ua.VariantType.String


def test_workspace_plc_csv_loads_deterministic_writable_variable_catalog() -> None:
    definitions = {item.name: item for item in load_variable_definitions(DEFAULT_CSV)}

    assert len(definitions) == 1561
    assert definitions["Robot_Home"].variant_type is ua.VariantType.Boolean
    assert definitions["Robot_任务允许写入"].variant_type is ua.VariantType.Boolean
    assert definitions["任务号"].variant_type is ua.VariantType.Int32
    assert definitions["S03取放料产品"].variant_type is ua.VariantType.Int32
    assert definitions["S07天平读数"].variant_type is ua.VariantType.Float
    assert definitions["S07位置10二维码[99]"].variant_type is ua.VariantType.Int16
