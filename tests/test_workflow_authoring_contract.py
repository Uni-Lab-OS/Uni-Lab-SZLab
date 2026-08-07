from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from unilabos.workflow.authoring_ast import AuthoringSyntaxError, parse_authoring_source


def test_all_package_workflows_compile_with_product_authoring_contract(
    repo_root: Path,
) -> None:
    """使用产品解析器验证整个 SZLab 工作流源码目录，而不是复刻其规则。"""

    package = yaml.safe_load((repo_root / "package.yaml").read_text(encoding="utf-8"))
    assert len(package["workflows"]) == 16

    programs = {}
    for entry in package["workflows"]:
        source_path = repo_root / entry["source"]
        try:
            programs[entry["workflow_uuid"]] = parse_authoring_source(
                python_source=source_path.read_text(encoding="utf-8"),
                expected_workflow_uuid=entry["workflow_uuid"],
            )
        except AuthoringSyntaxError as error:
            pytest.fail(f"{entry['source']}: {error.code}: {error.message}")

    s04 = programs["1bc5a151-445a-5a53-b24a-7a4b521ac60c"]
    assert [action.action_name for action in s04.actions] == [
        "submit_place_to_s04",
        "run_stirring",
        "submit_pick_from_s04",
    ]
    assert s04.outputs == ()
