# Windows Soak / Fault Matrix V2 (#140)

Generated: `2026-09-19T10:50:09.0464493+08:00`

- status: **SOAK_PASS** (18/18 scenarios passed)
- expected persisted snapshot_id: `dsv0-monitoring-20260919-8258e11a5b5065b8`
- final stop exit: `0`

## Scenarios

| scenario | result | detail |
|---|---|---|
| S01-clean-start | PASS | exit=0 health=200 latest=200 backend=6484 frontend=25860 |
| S02-warm-start | PASS | exit=0 health=200 snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 |
| S03-duplicate-start-reuse | PASS | exit=0 backend_unchanged=True frontend_unchanged=True |
| S04-api-crash-actionable-and-recovery | PASS | proxy_during_crash=502 recovery_exit=0 health=200 snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 |
| S05-api-crash-readback | PASS | snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1 (expected snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1) |
| S06-frontend-crash-and-recovery | PASS | frontend_during_crash=-1 recovery_exit=0 health=200 |
| S07-full-restart | PASS | stop=0 ports_down=True start=0 snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 |
| S08-full-restart-readback | PASS | snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1 (expected snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1) |
| S09-stale-pid-metadata | PASS | exit=0 health=200 new_backend=25708 |
| S10-foreign-frontend-port-failclosed | PASS | exit=13 foreign_alive=True pid_file_absent=True |
| S11-foreign-backend-port-failclosed | PASS | exit=14 foreign_alive=True |
| S12-corrupted-metadata-stop-refuses | PASS | stop=43 backend_health=200 ports_still_up=True |
| S13-restored-metadata-stop-succeeds | PASS | stop=0 ports_down=True |
| S14-missing-metadata-stop-refuses | PASS | stop=41 backend_health=200 ports_still_up=True |
| S15-missing-metadata-harness-recovery | PASS | stop_after_metadata_restore=0 |
| S16-browser-reopen | PASS | exit=0 browser=msedge.exe run_id_found=True no_demo=True available=True |
| S17-final-readback | PASS | snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1 (expected snapshot_id=dsv0-monitoring-20260919-8258e11a5b5065b8 tech=1 canonical=1) |
| S18-unrelated-processes-survive | PASS | python_sentinel=True node_sentinel=True |

## Process ownership invariants

- STOP/launcher own only command-line-verified launcher processes recorded in servers.pid
- foreign port occupants fail closed (exit 13/14) and always survive
- corrupted or missing runtime metadata never triggers a kill of unverified processes
- unrelated Python/Node processes survive every lifecycle scenario

## Blockers

- none

