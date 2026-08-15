"""Acceptance-scenario traceability (ARCH §15.1): every SPEC A1–A12 maps to real tests.

Parses docs/design/SPEC.md, extracts the scenario list, and asserts the mapped test
functions exist by name in the suite. A scenario whose mapped test disappears fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Scenario -> the test node(s) that encode it.
SCENARIO_TESTS = {
    "A1": ["tests/integration/test_cli.py::TestPackApplyCycle::test_full_cycle_a1",
           "tests/integration/test_apply.py::TestRoundTrip::test_a1_clean_target_apply"],
    "A2": ["tests/unit/test_provenance.py::TestClassification::test_rebaseline_only_pristine",
           "tests/unit/test_platform.py::TestTranslation::test_posix_to_windows"],
    "A3": ["tests/integration/test_pack_bundle.py::TestPack::test_no_plaintext_credentials_in_payload",
           "tests/integration/test_pack_bundle.py::TestPack::test_checklist_names_only"],
    "A4": ["tests/integration/test_pack_bundle.py::TestVault::test_vault_round_trip",
           "tests/integration/test_pack_bundle.py::TestVault::test_wrong_passphrase_clean_error"],
    "A5": ["tests/integration/test_apply.py::TestCrashRollback::test_a5_crash_mid_apply_then_rollback"],
    "A6": ["tests/integration/test_apply.py::TestConflicts::test_a6_keep_policy"],
    "A7": ["tests/unit/test_provenance.py::TestClassification::test_six_tags",
           "tests/unit/test_provenance.py::TestDiffs::test_config_diff_masks_credentials"],
    "A8": ["tests/integration/test_apply.py::TestRoundTrip::test_cron_claims_scrubbed"],
    "A9": ["tests/integration/test_pack_bundle.py::TestHostileBundles::test_traversal_member",
           "tests/integration/test_pack_bundle.py::TestHostileBundles::test_bomb_guard"],
    "A10": ["tests/unit/test_report_verify.py::TestReports::test_html_self_contained_and_escaped",
            "tests/unit/test_report_verify.py::TestReports::test_redaction_masks_home_and_user"],
    "A11": ["tests/integration/test_cli.py::TestScanDiffDeps::test_deps_predictive",
            "tests/unit/test_deps.py::TestPredictive::test_windows_member_legality"],
    "A12": ["tests/integration/test_cli.py::TestDeepScan::test_generate_then_ingest_a12"],
}


def test_spec_lists_twelve_scenarios():
    spec = (ROOT / "docs" / "design" / "SPEC.md").read_text(encoding="utf-8")
    scenarios = set(re.findall(r"\*\*A(\d+) —", spec))
    assert {str(i) for i in range(1, 13)} <= scenarios


def test_every_scenario_has_living_tests():
    for scenario, nodes in SCENARIO_TESTS.items():
        assert nodes, scenario
        for node in nodes:
            file_part, func_part = node.split("::", 1)
            path = ROOT / file_part
            assert path.is_file(), f"{scenario}: {file_part} missing"
            func_name = func_part.split("::")[-1]
            assert func_name in path.read_text(encoding="utf-8"), \
                f"{scenario}: {func_name} not found in {file_part}"


def test_banned_apis_absent():
    """AST-lite bans from ARCH §15.3: no extractall, no tkinter/yaml imports in src."""
    src = ROOT / "src" / "talaria"
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if ".extractall(" in text:
            offenders.append(f"{path}: extractall")
        if re.search(r"^\s*import tkinter|^\s*from tkinter", text, re.M):
            offenders.append(f"{path}: tkinter")
        if re.search(r"^\s*import yaml\b|^\s*from yaml\b", text, re.M):
            offenders.append(f"{path}: pyyaml")
    assert not offenders, offenders


def test_stub_is_py27_parseable():
    """The __main__ stub must parse on ancient Pythons (no f-strings etc.)."""
    import ast

    text = (ROOT / "src" / "talaria" / "__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.JoinedStr), "f-string in the 2.7 stub"
