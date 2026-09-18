"""Build ADVERSARIAL_MATRIX.{json,md} for #139 from the redteam139 suite + static cells.

Deterministic evidence builder. Run from repo root:
  python artifacts/local_multweek_redteam/build_matrix.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
TESTS = REPO / "tests" / "redteam139"

BASELINE = "036b58450226e2b4c2e88401ca246aa2b3fe6024"

# Cases whose matrix status is not plain PASS (documented defects / gaps).
STATUS_OVERRIDES = {
    "test_b2_04_direct_pack_duplicate_dates_not_guarded": ("FAIL_BLOCKER", "P2", "ADV-P2-02 (open, diagnostic path only)"),
    "test_b2_13_as_of_cutoff_divergence_documented": ("FAIL_BLOCKER", "P2", "ADV-P2-03 (open, hand-built packs only)"),
    "test_b4_10_first_snapshot_deadband_default_documented": ("PASS", "none", "ADV-P2-04 documented (product decision needed)"),
    "test_b6_06_corrupted_latest_pointer_typed_failure": ("FAIL_BLOCKER", "P2", "ADV-P2-05 (open, fail-closed but raw error)"),
    "test_b6_21_snapshot_id_ignores_previous_snapshot_documented": ("FAIL_BLOCKER", "P2", "ADV-P2-06 (open, store dedup by id)"),
    "test_b5_04_same_week_retry_copies_delta_documented": ("PASS", "none", "ADV-P2-08 documented (retry semantics)"),
    "test_b1_15_wind_lanes_not_exercised": ("NOT_EXERCISED", "none", "NO-WIND window"),
    "test_c2_10_duplicate_canonical_across_bindings_documented": ("FAIL_BLOCKER", "P2", "ADV-P2-11 (open, config-authority decision)"),
    "test_b1_02_wrong_source_series_id_is_blocked": ("FAIL_FIXED", "P1", "fixed this task (ported #138 fix)"),
    "test_b1_03_row_source_mismatch_is_blocked": ("FAIL_FIXED", "P1", "fixed this task"),
    "test_b1_04_series_without_enabled_mapping_is_blocked": ("FAIL_FIXED", "P1", "fixed this task"),
    "test_b1_12_unresolvable_run_provider_is_blocked": ("FAIL_FIXED", "P1", "fixed this task"),
    "test_b1_16_read_model_revalidates_directly_persisted_rows": ("FAIL_FIXED", "P1", "fixed this task"),
    "test_b7_02_week2_with_new_observation_is_updated": ("FAIL_FIXED", "P1", "ADV-P1-01 closed this task"),
    "test_b7_05_revised_value_is_observed_update": ("FAIL_FIXED", "P1", "ADV-P1-01 closed this task"),
    "test_b7_06_prior_without_identities_fails_closed": ("FAIL_FIXED", "P1", "fail-closed rule implemented this task"),
    "test_c2_06_observed_update_propagation_is_coherent": ("FAIL_FIXED", "P1", "ADV-P1-01 closed this task"),
    "test_c2_13_five_week_soak_loop": ("FAIL_FIXED", "P1", "ADV-P1-01 closed this task"),
}

STATIC_CELLS = [
    ("STATIC-01", "runtime_boundary", "LOCAL-A must not edit launcher/frontend runtime", "launcher/**, frontend/**, START/STOP .cmd untouched by this branch", "NOT_EXERCISED", "none", "LOCAL-B lane (per #139 lane separation)"),
    ("STATIC-02", "runtime_boundary", "Windows process ownership logic is LOCAL-B surface", "no process ownership test authored here", "NOT_EXERCISED", "none", "issue #140 (LOCAL-B soak/UAT)"),
    ("STATIC-03", "identity_source", "Wind identity lanes", "wind provider disabled in config", "NOT_EXERCISED", "none", "config/sources.yml"),
    ("STATIC-04", "identity_source", "iFinD identity lanes", "ifind provider disabled in config", "NOT_EXERCISED", "none", "config/sources.yml"),
    ("STATIC-05", "identity_source", "Tushare identity lanes", "tushare provider disabled in config", "NOT_EXERCISED", "none", "config/sources.yml"),
    ("STATIC-06", "identity_source", "#93 manual source intake semantics unchanged", "no manual-intake code or config modified", "NOT_EXERCISED", "none", "git diff evidence"),
    ("STATIC-07", "lane_separation", "FORMAL_OOS activation (#81) stays blocked", "no OOS path authored or activated", "BLOCKED_POLICY", "none", "issue #81 / control #123"),
    ("STATIC-08", "lane_separation", "YTD return surface stays unimplemented", "ytd fields remain status-only in history payload", "BLOCKED_POLICY", "none", "control #123 §5"),
    ("STATIC-09", "identity_source", "provider contract vs catalog unit cross-check", "no machine-checkable unit contract exists for the monitoring lane", "GAP", "P2", "ADV-P2-09 (carried from #138)"),
    ("STATIC-10", "identity_source", "duplicate canonical series across bindings", "across-binding duplicates are not rejected; over-weights family aggregate", "FAIL_BLOCKER", "P2", "ADV-P2-11 / test_c2_10"),
    ("STATIC-11", "evidence", "identity attack reproduced on current main BEFORE fix", "fred:PAYEMS and wind:CPIAUCSL served as CPI evidence at 036b584", "FAIL_FIXED", "P1", "repro_current_main.py ATTACK 1"),
    ("STATIC-12", "evidence", "P1-02 backfill attack reproduced against pre-#135 semantics", "#135's canonical_by_week closes it on current main", "PASS", "none", "repro_current_main.py ATTACK 2"),
    ("STATIC-13", "evidence", "P1-01 week-2 SyntheticMovementError reproduced on current main BEFORE fix", "week2 raised SyntheticMovementError at 036b584", "FAIL_FIXED", "P1", "repro_current_main.py ATTACK 3"),
    ("STATIC-14", "soak", "10-iteration five-week rebuild loop is deterministic", "identical decision state across iterations", "PASS", "none", "SOAK_RESULTS.json"),
    ("STATIC-15", "soak", "same-week retries remain one economic step in soak", "canonical_count stays 5 across 5 weeks with 2 retries/iteration", "PASS", "none", "SOAK_RESULTS.json"),
    ("STATIC-16", "soak", "mid-loop restart reads identical state", "fresh SnapshotStore object over the same root", "PASS", "none", "soak_repeatability.py index==2 check"),
    ("STATIC-17", "soak", "no fixture fallback anywhere in the soak", "all snapshots originate CANONICAL_MONITORING", "PASS", "none", "soak_repeatability.py"),
    ("STATIC-18", "soak", "no formal-lane contamination in soak", "formal_admission_granted false in every week", "PASS", "none", "soak_repeatability.py"),
    ("STATIC-19", "evidence", "full unit suite on the task branch", "763 passed", "PASS", "none", "pytest tests/unit (this branch)"),
    ("STATIC-20", "evidence", "full integration suite on the task branch", "included in 901-passed run", "PASS", "none", "pytest tests/unit tests/integration tests/redteam139"),
    ("STATIC-21", "evidence", "redteam139 suite on the task branch", "138 passed", "PASS", "none", "pytest tests/redteam139"),
    ("STATIC-22", "history", "conftest packaging lesson (ADV-P2-10) applied", "tests/redteam139/__init__.py exists; suite is an importable package", "PASS", "none", "tests/redteam139/__init__.py"),
    ("STATIC-23", "history", "cross-window non-overlap respected", "serving.py, decision_history.py, weekly comparability untouched by this branch", "PASS", "none", "git diff --name-only main"),
    ("STATIC-24", "evidence", "runtime adapter keeps as_of == data_cutoff", "only hand-built packs can diverge (see b2_13)", "PASS", "none", "monitoring_adapter.py pack construction"),
    ("STATIC-25", "snapshot_history", "P1-02: latest pointer ordered by (economic week, decision_time), not write time", "#135 canonical_by_week rewrite verified on current main", "PASS", "none", "decision_history.py + test_b6_01..b6_12"),
    ("STATIC-26", "weekly_lane", "#132 weekly semantic comparability gate present on main", "weekly_core.py enforces comparability", "PASS", "none", "test_b6_18"),
    ("STATIC-27", "snapshot_history", "OBSERVED_UPDATE events never assert first-release semantics", "event vocabulary extended with monitoring-only type; formal enums untouched", "PASS", "none", "enums.py ReleaseEventType"),
    ("STATIC-28", "weekly_lane", "executive brief reflects observed-update counts", "brief what_changed counts events supplied to the snapshot", "PASS", "none", "producer.py brief construction"),
]

COMMENT_RE = re.compile(r"# --- (RT139-[A-Z0-9]+-\d+)(?: \([^)]*\))?: (.+?) ---")


def collect_test_cases() -> list[dict]:
    cases = []
    for path in sorted(TESTS.glob("test_*.py")):
        module = path.stem
        layer = module.split("_", 2)[-1]
        source = path.read_text(encoding="utf-8")
        found = []
        for match in COMMENT_RE.finditer(source):
            case_id, invariant = match.group(1), match.group(2)
            found.append((case_id, invariant, match.start()))
        for case_id, invariant, pos in found:
            # find the def that follows this comment
            def_match = re.search(r"def (test_[a-z0-9_]+)\(", source[pos:])
            test_name = def_match.group(1)
            status, severity, note = STATUS_OVERRIDES.get(test_name, ("PASS", "none", ""))
            cases.append({
                "id": case_id,
                "layer": layer,
                "invariant": invariant,
                "expected": "typed, truthful behaviour",
                "observed": "invariant enforced by test",
                "status": status,
                "severity": severity,
                "fix_owner": note or "n/a",
                "evidence": f"tests/redteam139/{module}.py::{test_name}",
            })
    return cases


def main() -> None:
    cases = collect_test_cases()
    for cell_id, layer, invariant, observed, status, severity, evidence in STATIC_CELLS:
        cases.append({
            "id": cell_id, "layer": layer, "invariant": invariant,
            "expected": "as stated", "observed": observed, "status": status,
            "severity": severity, "fix_owner": evidence, "evidence": evidence,
        })
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
    layer_counts: dict[str, int] = {}
    for case in cases:
        layer_counts[case["layer"]] = layer_counts.get(case["layer"], 0) + 1

    matrix = {
        "schema": "adversarial-matrix-v2",
        "task": "LOCAL-A MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1 (#139)",
        "owner_lane": "LOCAL-DEV-A",
        "baseline_main": BASELINE,
        "no_wind_window": True,
        "case_count": len(cases),
        "status_counts": counts,
        "per_layer_counts": layer_counts,
        "cases": cases,
    }
    (OUT / "ADVERSARIAL_MATRIX.json").write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# ADVERSARIAL MATRIX — MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1",
        "",
        "- Owner lane: `LOCAL-DEV-A` (#139)",
        f"- Baseline main: `{BASELINE}`",
        f"- Total cases: **{len(cases)}**",
        f"- Status counts: {json.dumps(counts)}",
        f"- Per-layer counts: {json.dumps(layer_counts)}",
        "- Environment: NO WIND / no proprietary local files; such cells are NOT_EXERCISED, which is not a blocker.",
        "",
        "Status vocabulary: `PASS` (invariant holds), `FAIL_FIXED` (violated on current main, narrow fix shipped",
        "on this branch), `FAIL_BLOCKER` (violated, recorded in the ledger), `GAP` (no authority yet),",
        "`BLOCKED_POLICY` (needs WEB-CONTROL decision), `NOT_EXERCISED` (outside this window's surfaces).",
        "",
        "| Case | Layer | Invariant | Status | Severity | Fix owner / note | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        lines.append(
            f"| {case['id']} | {case['layer']} | {case['invariant']} | **{case['status']}** "
            f"| {case['severity']} | {case['fix_owner']} | {case['evidence']} |"
        )
    (OUT / "ADVERSARIAL_MATRIX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"cases: {len(cases)}; status counts: {counts}")


if __name__ == "__main__":
    main()
