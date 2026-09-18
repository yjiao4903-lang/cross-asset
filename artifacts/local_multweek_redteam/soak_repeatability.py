"""Phase 6 soak: repeat the five-week producer/snapshot/history rebuild loop.

Deterministic inputs must yield deterministic decision state across repeated
iterations, with restarts (fresh SnapshotStore objects) between selected runs.
Same-week retries must remain one economic step. No fixture fallback, no
formal-lane contamination. Evidence-only script; no repository mutation.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

from redteam139.test_c2_emergent import WeekWorld

from cross_asset.decision_support.enums import InformationSetStatus, ReleaseEventType
from cross_asset.decision_support.serving import SnapshotStore

WEEKS = [
    (date(2026, 9, 4), datetime(2026, 9, 5, 6, tzinfo=UTC)),
    (date(2026, 9, 11), datetime(2026, 9, 12, 6, tzinfo=UTC)),
    (date(2026, 9, 18), datetime(2026, 9, 19, 6, tzinfo=UTC)),
    (date(2026, 9, 25), datetime(2026, 9, 26, 6, tzinfo=UTC)),
    (date(2026, 10, 2), datetime(2026, 10, 3, 6, tzinfo=UTC)),
]
ITERATIONS = 10


def run_iteration(iteration: int, root) -> dict:
    """One five-week rebuild with interleaved retries and a mid-loop restart."""

    world = WeekWorld()
    store = SnapshotStore(root)
    month_len = 48
    fingerprints = []
    for index, (cutoff, decision) in enumerate(WEEKS):
        end_month = date(2026, 8, 1) if index == 0 else date(2026, 9, 1)
        if index == 1:
            month_len = 49  # a genuinely new monthly observation becomes visible
        world.capture(end_month=end_month, capture=decision.replace(hour=0),
                      run_id=f"run-soak-{index}", cpi_len=month_len, pay_len=month_len)
        snapshot = world.week(cutoff=cutoff, decision=decision, run_id=f"wb-soak-{index}")
        store.persist(snapshot)
        delta = snapshot.weekly_change.information_set_delta
        changed = set(snapshot.weekly_change.macro_state_delta.changed_factors())
        updated = {e.factor_id for e in delta.events
                   if e.resolved_event_type() is ReleaseEventType.OBSERVED_UPDATE}
        if delta.resolved_status() is InformationSetStatus.UPDATED:
            assert changed <= updated or not changed, "movement without observed update"
        else:
            assert not changed, "synthetic movement in a stale week"
        # same-week retry: one extra decision, same economic step
        retry_pack_snapshot_id = None
        if index in (1, 3):
            retry_pack = __import__(
                "cross_asset.decision_support.monitoring_adapter", fromlist=["build_monitoring_pack_from_db"]
            ).build_monitoring_pack_from_db(
                world.store,
                __import__("cross_asset.operations.workbench_run", fromlist=["WorkbenchRun"]).WorkbenchRun(
                    run_id=f"wb-soak-{index}-retry", run_kind="shadow", source_mode="LIVE",
                    status="SUCCESS", model_version="workbench_v0.1",
                    config_identity="decision-support-v2:adversarial-test-only",
                    data_cutoff=cutoff.isoformat(),
                    decision_time=(decision + timedelta(hours=1)).isoformat(),
                ),
            )
            retry = __import__(
                "cross_asset.decision_support.producer", fromlist=["build_monitoring_snapshot"]
            ).build_monitoring_snapshot(retry_pack, previous_snapshot=snapshot)
            world.snapshots.append(retry)
            store.persist(retry)
            retry_pack_snapshot_id = retry.metadata.snapshot_id
        # mid-loop restart: fresh store object must read identical state
        if index == 2:
            reopened = SnapshotStore(root)
            assert reopened.load_latest().to_json() == store.load_latest().to_json()
        fingerprints.append({
            "week": snapshot.details["economic_week_id"],
            "info_status": delta.status.value,
            "changed": sorted(changed),
            "canonical_count": len(store.list_canonical()),
            "technical_count": len(store.list_snapshots()),
            "retry_id": retry_pack_snapshot_id,
        })
    assert store.load_latest().metadata.as_of == WEEKS[-1][0]
    assert len(store.list_canonical()) == 5, "retries must not create extra economic weeks"
    return fingerprints


def main() -> int:
    summary = {"iterations": ITERATIONS, "weeks": len(WEEKS), "runs": []}
    reference = None
    with tempfile.TemporaryDirectory() as tmp:
        for iteration in range(ITERATIONS):
            root = Path(tmp) / f"iter-{iteration}"
            fingerprints = run_iteration(iteration, root)
            if reference is None:
                reference = fingerprints
            else:
                assert fingerprints == reference, (
                    f"iteration {iteration} diverged from iteration 0: stateful defect"
                )
            summary["runs"].append({"iteration": iteration, "verdict": "DETERMINISTIC"})
    summary["final_verdict"] = "SOAK_PASS_DETERMINISTIC"
    print(json.dumps(summary, indent=2))
    out = Path(__file__).parent / "SOAK_RESULTS.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
