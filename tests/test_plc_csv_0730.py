from __future__ import annotations

import csv
import json
from pathlib import Path

from szlab_poly_studio.devices.szlab_poly_plc.device import DEFAULT_CSV_NAME

PLC_DEVICE_CLASSES = {
    "szlab_mixer_robot",
    "szlab_mixer_stirrer",
    "szlab_mixer_photoshotting",
    "szlab_mixer_pump",
    "szlab_s07_solid_addition",
    "szlab_s08_cap_station",
    "szlab_mixer_pipetting_station",
}

# 仅保留在旧运行配置或兼容常量中，当前动作与工作流均不读写。
LEGACY_UNUSED_NAMES = {
    "PLC_R任务号",
    "S03_1取料编号",
    "S03_1放料编号",
}


def _read_plc_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-16", newline="") as csv_file:
        return list(csv.DictReader(csv_file, delimiter="\t"))


def _read_station_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def test_0730_csv_is_a_strict_superset_of_0702_and_station_csvs(
    repo_root: Path,
) -> None:
    devices_root = repo_root / "szlab_poly_studio" / "devices"
    plc_root = devices_root / "szlab_poly_plc"
    old_path = plc_root / "szlab_plc_0702.csv"
    new_path = plc_root / "szlab_plc_0730.csv"
    old_rows = _read_plc_csv(old_path)
    new_rows = _read_plc_csv(new_path)
    station_paths = [
        devices_root / "szlab_mixer_stirrer" / "magnetic_stirring_nodes.csv",
        devices_root / "szlab_mixer_photoshotting" / "photoshotting_nodes.csv",
        devices_root / "szlab_mixer_pump" / "pump_nodes.csv",
        devices_root / "szlab_s07_solid_addition" / "s07_nodes.csv",
        devices_root / "szlab_s08_cap_station" / "decap_s08_nodes.csv",
        devices_root
        / "szlab_mixer_pipetting_station"
        / "pipetting_station_nodes.csv",
    ]

    assert DEFAULT_CSV_NAME == "szlab_plc_0730.csv"
    assert new_rows[: len(old_rows)] == old_rows

    old_names = {
        row["变量名"].strip() for row in old_rows if row["变量名"].strip()
    }
    new_names = [
        row["变量名"].strip() for row in new_rows if row["变量名"].strip()
    ]
    station_names = {
        row["变量名"].strip()
        for station_path in station_paths
        for row in _read_station_csv(station_path)
        if row["变量名"].strip()
    }

    assert len(new_names) == len(set(new_names))
    assert station_names <= set(new_names)
    expected_s07_additions = {
        f"S07位置{position}二维码[{index}]"
        for position in range(1, 11)
        for index in range(30, 100)
    }
    assert set(new_names) - old_names == {
        "S03_1取料编号",
        "S03_1放料编号",
        "PLC_R任务号",
        "S07天平读数",
        "S07数据清空",
        *expected_s07_additions,
    }


def test_0731_real_plc_csv_covers_the_current_driver_contract(
    repo_root: Path,
) -> None:
    plc_root = repo_root / "szlab_poly_studio" / "devices" / "szlab_poly_plc"
    simulator_rows = _read_plc_csv(plc_root / "szlab_plc_0730.csv")
    real_plc_rows = _read_plc_csv(plc_root / "szlab_plc_0731.csv")

    simulator_by_name = {
        row["变量名"].strip(): row
        for row in simulator_rows
        if row["变量名"].strip()
    }
    real_plc_by_name = {
        row["变量名"].strip(): row
        for row in real_plc_rows
        if row["变量名"].strip()
    }

    assert len(real_plc_by_name) == len(real_plc_rows)
    assert set(simulator_by_name) - set(real_plc_by_name) == (
        LEGACY_UNUSED_NAMES
    )
    assert set(real_plc_by_name) - set(simulator_by_name) == {
        "S04数据清空",
        "S06数据清空",
        "S08数据清空",
        "S09数据清空",
        "S12数据清空",
    }

    type_changes = {
        name: (
            simulator_by_name[name]["数据类型"].strip(),
            real_plc_by_name[name]["数据类型"].strip(),
        )
        for name in set(simulator_by_name) & set(real_plc_by_name)
        if simulator_by_name[name]["数据类型"].strip()
        != real_plc_by_name[name]["数据类型"].strip()
    }
    assert type_changes == {
        f"S07位置{position}二维码": ("INT[30]", "INT[100]")
        for position in range(1, 11)
    }
    assert real_plc_by_name["S07天平读数"]["数据类型"].strip() == "REAL"
    assert real_plc_by_name["S09天平读数"]["数据类型"].strip() == "REAL"
    assert real_plc_by_name["S09天平读数稳定"]["数据类型"].strip() == "BOOL"
    assert all(
        f"S07位置{position}二维码[{index}]" in real_plc_by_name
        for position in range(1, 11)
        for index in range(100)
    )


def test_graphs_configure_only_the_main_plc_as_an_opc_client(
    repo_root: Path,
) -> None:
    graph_root = repo_root / "deployment" / "graphs"
    expected_csv_by_graph = {
        "szlab-local-debug.json": "szlab_plc_0730.csv",
        "szlab-ideawit-sim.json": "szlab_plc_0731.csv",
    }
    for filename, expected_csv in expected_csv_by_graph.items():
        graph = json.loads((graph_root / filename).read_text(encoding="utf-8"))
        devices = {
            node["id"]: node
            for node in graph["nodes"]
            if node["type"] == "device"
        }
        assert devices["szlab_poly_plc"]["config"]["csv_path"] == expected_csv
        for device_class in PLC_DEVICE_CLASSES:
            config = devices[device_class]["config"]
            assert config["plc_device_id"] == "szlab_poly_plc"
            assert "url" not in config
            assert "csv_path" not in config
            assert "auto_connect" not in config
