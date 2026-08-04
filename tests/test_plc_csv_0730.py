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


def test_graphs_configure_only_the_main_plc_as_an_opc_client(
    repo_root: Path,
) -> None:
    graph_root = repo_root / "deployment" / "graphs"
    for filename in ("szlab-local-debug.json", "szlab-ideawit-sim.json"):
        graph = json.loads((graph_root / filename).read_text(encoding="utf-8"))
        devices = {
            node["id"]: node
            for node in graph["nodes"]
            if node["type"] == "device"
        }
        assert devices["szlab_poly_plc"]["config"]["csv_path"] == (
            "szlab_plc_0730.csv"
        )
        for device_class in PLC_DEVICE_CLASSES:
            config = devices[device_class]["config"]
            assert config["plc_device_id"] == "szlab_poly_plc"
            assert "url" not in config
            assert "csv_path" not in config
            assert "auto_connect" not in config
