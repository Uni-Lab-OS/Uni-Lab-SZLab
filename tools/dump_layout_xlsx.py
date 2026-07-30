#!/usr/bin/env python3
"""把布局表格（理论交点测距结果.xlsx）原样打印出来，用于核对零件位置与模型文件。

只用标准库解析 xlsx（zip + XML），避免为一次性核对引入 openpyxl 依赖。
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{NS}t"))
        for item in root.findall(f"{NS}si")
    ]


def sheet_names(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        element.attrib["Id"]: element.attrib["Target"]
        for element in rels
    }
    names: list[tuple[str, str]] = []
    for sheet in workbook.iter(f"{NS}sheet"):
        rel = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        target = targets.get(str(rel), "")
        path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
        names.append((sheet.attrib.get("name", "?"), path))
    return names


def read_rows(
    archive: zipfile.ZipFile, path: str, strings: list[str]
) -> list[dict[str, str]]:
    root = ElementTree.fromstring(archive.read(path))
    rows: list[dict[str, str]] = []
    for row in root.iter(f"{NS}row"):
        cells: dict[str, str] = {}
        for cell in row.iter(f"{NS}c"):
            column = re.sub(r"\d", "", cell.attrib.get("r", ""))
            kind = cell.attrib.get("t")
            if kind == "inlineStr":
                text = "".join(
                    node.text or "" for node in cell.iter(f"{NS}t")
                )
            else:
                value = cell.find(f"{NS}v")
                text = "" if value is None or value.text is None else value.text
                if kind == "s" and text:
                    text = strings[int(text)]
            if text:
                cells[column] = text.replace("\n", " / ")
        if cells:
            rows.append(cells)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.home() / "Documents" / "理论交点测距结果.xlsx",
    )
    args = parser.parse_args()

    with zipfile.ZipFile(args.path) as archive:
        strings = shared_strings(archive)
        for name, path in sheet_names(archive):
            rows = read_rows(archive, path, strings)
            print(f"=== sheet {name} ({len(rows)} rows) ===")
            for index, cells in enumerate(rows, start=1):
                joined = "  ".join(
                    f"{column}={value}" for column, value in sorted(cells.items())
                )
                print(f"{index:3d} | {joined}")


if __name__ == "__main__":
    main()
