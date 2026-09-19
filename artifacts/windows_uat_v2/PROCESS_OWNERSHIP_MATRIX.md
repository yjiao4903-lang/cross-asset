# Process Ownership Matrix (#140)

Generated: `2026-09-19T10:50:09.0517908+08:00`

## Invariants

- STOP/launcher own only command-line-verified launcher processes recorded in servers.pid
- foreign port occupants fail closed (exit 13/14) and always survive
- corrupted or missing runtime metadata never triggers a kill of unverified processes
- unrelated Python/Node processes survive every lifecycle scenario

| scenario | result | detail |
|---|---|---|
| S03-duplicate-start-reuse | PASS | exit=0 backend_unchanged=True frontend_unchanged=True |
| S09-stale-pid-metadata | PASS | exit=0 health=200 new_backend=25708 |
| S10-foreign-frontend-port-failclosed | PASS | exit=13 foreign_alive=True pid_file_absent=True |
| S11-foreign-backend-port-failclosed | PASS | exit=14 foreign_alive=True |
| S12-corrupted-metadata-stop-refuses | PASS | stop=43 backend_health=200 ports_still_up=True |
| S13-restored-metadata-stop-succeeds | PASS | stop=0 ports_down=True |
| S14-missing-metadata-stop-refuses | PASS | stop=41 backend_health=200 ports_still_up=True |
| S15-missing-metadata-harness-recovery | PASS | stop_after_metadata_restore=0 |
| S18-unrelated-processes-survive | PASS | python_sentinel=True node_sentinel=True |

