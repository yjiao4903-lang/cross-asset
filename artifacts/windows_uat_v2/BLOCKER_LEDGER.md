# Blocker Ledger — WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2 (#140)

Generated: `2026-09-19T02:52:39.322783+00:00`

| id | class | status | detail |
|---|---|---|---|
| B1 | BRANCH_ARTIFACT_CORRUPTION | RESOLVED | launcher/tests/windows_soak_uat_v2.ps1 was committed as a corrupted blob in c8e3b3a (valid PowerShell prefix ~9.6KB followed by ~18.7KB of binary garbage; not a compression stream). Rewritten as a working soak/fault-matrix driver; full matrix executed with SOAK_PASS 18/18. |
| B2 | CODE_PATH_DEFECT | RESOLVED | real_snapshot_uat_v2.py invoked the snapshot_cli subprocess while the parent still held the DuckDB connection; Windows single-writer lock made snapshot build fail (IOException). Parent connection is now closed before the subprocess opens the same DB; snapshot build succeeds via the normal --db + --run-id path. |
| B3 | FRONTEND_USABILITY_DEFECT | RESOLVED | OverviewPage crashed on the real MONITORING snapshot when an asset view has an empty drivers array (topDriver undefined -> React unmount). Fixed to render a truthful 'no driver data' placeholder. Allowed under the frontend freeze as a material usability fix on the real-snapshot path; no business logic added. |
| B4 | FRONTEND_USABILITY_DEFECT | RESOLVED | Header overflow after displaying producer-owned metadata.snapshot_id (long unbreakable decision_time span). Fixed with truncate/overflow-hidden; snapshot_id is now visible in the UI (data-testid=snapshot-id) so browser and API provably share one identity. |
| B5 | HARNESS_WAIT_SEMANTICS | RESOLVED | PowerShell `& script / Out-Null` waits for stdout EOF (held open by launcher's redirected grandchildren) and Start-Process -Wait waits for the whole descendant tree. Both drivers now poll $proc.HasExited to wait for the launcher/stopper process only. |
| B6 | ENVIRONMENT_GAP | RESOLVED | No Node.js existed on the workstation (launcher requires Node for the static server/reverse proxy). Installed user-space Node v24.21.0 + npm 11.19.0 under tools/node (zip extract; no admin, no registry/firewall mutation); recorded in ENVIRONMENT evidence and ignored via .gitignore. |
| B7 | REAL_PROVIDER_SOURCE_COVERAGE | OPEN / ROUTED | Bound series CN_EQ_LARGE, COPPER, GOLD have no accepted public-provider source on this lane (not fetchable via FRED/Yahoo monitoring adapters). Snapshot is REAL_SNAPSHOT_PERSISTED_PARTIAL with truthful MISSING/UNKNOWN semantics; gate not lowered, no zero-fill. Route to WEB-CONTROL/LOCAL-A if user-owned source files become available. |
| B8 | DIAGNOSTIC_NOTE | INFORMATIONAL | A per-user system proxy (127.0.0.1:17891) is configured in the Windows registry. Direct HTTPS egress to nodejs.org/FRED/Yahoo works without it; local loopback health checks bypass proxying (DefaultWebProxy cleared in harness). No proxy substitution was made in provider semantics. |
| B9 | FORMAL_BOUNDARY_CHECK | NONE | No formal-admission violations: acceptance registry rows 0, every series provenance formal_admission_granted=false, ingestion runs and snapshot lane MONITORING-only. |

**status:** REAL_SNAPSHOT_UAT_PASS_WITH_PARTIAL_SOURCE_COVERAGE / SOAK_PASS / NO_RUNTIME_BLOCKERS_OPEN
