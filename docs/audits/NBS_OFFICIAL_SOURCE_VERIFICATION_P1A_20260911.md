# NBS Official Source Verification — P1A (CN_PMI / CN_CPI / CN_PPI)

- **Issue:** #103 — [P1A] Official NBS public-data verification for CN_PMI/CPI/PPI
- **Executor:** LOCAL-DEV-B
- **Baseline (only):** `48bcc6cdd32943d9914452a6aba3667198cf1b35` (`main`)
- **Branch:** `local-b/p1a-nbs-official` (isolated worktree)
- **Captured on:** 2026-09-11 (all pages fetched via plain HTTP GET; no authentication, no browser automation, no anti-bot bypass attempted or used)

## Determination (do not downgrade standards)

| Series | Status | Reason |
|---|---|---|
| CN_PMI | `PARTIAL` | Semantics resolved (index level, 50 baseline, per `config/macro.yml`); forward monthly window (rolling 13 months) retrievable from official release attachment via plain HTTP; **full-history durable series NOT available** — the only full-history route (data.stats.gov.cn API) returns reproducible 403, and backfill would require brittle historical-page scraping. |
| CN_CPI | `BLOCKED` | `raw_unit`/`derived_unit` remain `UNRESOLVED` in `config/macro.yml`; Issue #103 forbids resolving semantics merely because data is downloadable. Release provides current-month snapshot only; full-history API 403. |
| CN_PPI | `BLOCKED` | Same as CN_CPI: semantics `UNRESOLVED`; current-month snapshot only; full-history API 403. |

**Overall verdict: `OFFICIAL_LANE_BLOCKED` — evidence-only handoff, no collector code implemented.**

The official full-history structured route (data.stats.gov.cn) is not machine-accessible without forbidden circumvention. The accessible route (stats.gov.cn press releases + official Excel attachments) carries only a trailing window per release, which is insufficient for a durable research series and cannot be backfilled without building the exact "brittle scraper" the Issue instructs to avoid. All three series stay on Lane B (manual export).

---

## Captured evidence (official NBS properties only)

Captured raw files archived in this branch under `evidence/`; SHA-256 below (sha256sum of raw bytes as downloaded).

| File | SHA-256 | Bytes | Source URL (official) |
|---|---|---|---|
| `evidence/zxfb_index_20260911.html` | `86e268dacd7eaeae6a354b6fae1802626dc45edf772f1bb3e025047555f78a71` | 82928 | https://www.stats.gov.cn/sj/zxfb/ |
| `evidence/zxfb_index_10.html` | `be18fca3f08320ff8c9eb003acea7e12a446cd6b76028240467047d230c6bf20` | 83074 | https://www.stats.gov.cn/sj/zxfb/index_10.html |
| `evidence/zxfb_index_20.html` | `73a159177c5dfb1bc55bc81d2ac5d1dbb0462d5e2c080e91307f151554d80cc6` | 84090 | https://www.stats.gov.cn/sj/zxfb/index_20.html |
| `evidence/pmi_release_202608.html` | `f626372ab9154754cd8ea0a372450fd067714d567e618c2a45130d7749363e3b` | 421871 | https://www.stats.gov.cn/sj/zxfb/202608/t20260831_1965154.html |
| `evidence/pmi_attachment.xls` | `7ac612fa42b562fa27b4212d6b43b31fa9c0fd14e6a563bd5f385e735b629a2f` | 44032 | https://www.stats.gov.cn/sj/zxfb/202608/P020260831316826769515.xls |
| `evidence/cpi_release_202608.html` | `ae078538a1fc8450a0ad2759397503356321d79103f04fa9d09668358921f8f8` | 262277 | https://www.stats.gov.cn/sj/zxfb/202609/t20260909_1965263.html |
| `evidence/cpi_attachment.xlsx` | `01573e3b8cc82f614281c401ee6bb14f2d4d9ff18180931883ba3104b0360b64` | 11881 | https://www.stats.gov.cn/sj/zxfb/202609/P020260909324498220909.xlsx |
| `evidence/ppi_release_202608.html` | `7ffd7f32a0900c380c1aeee923038a6a282faec91de50afebf341176a4a48aed` | 283114 | https://www.stats.gov.cn/sj/zxfb/202609/t20260909_1965262.html |
| `evidence/ppi_attachment.xlsx` | `d2c39eb51575ea97e41bc26bc09a61e3904baf76f648488936e6b9f7a68c3baf` | 12009 | https://www.stats.gov.cn/sj/zxfb/202609/P020260909333517855845.xlsx |

All of the above returned HTTP 200 with a standard User-Agent header only. The large HTML captures are reproducible from the stable official URLs above; hashes are recorded here for later independent audit.

### Blocked official endpoint (reproducible)

| Endpoint | Result | Evidence |
|---|---|---|
| `https://data.stats.gov.cn/easyquery.htm?m=QueryData&dbcode=hgyd&rowcode=zb&colcode=sj&wds=[]&dfwds=...` | HTTP **403 Forbidden** (UrlACL) with UA + Referer headers | Reproduced 2026-09-11; no session/cookie/JS flow attempted because any bypass would constitute forbidden anti-bot circumvention per Issue #103 |

---

## Fact tables (12 items per series)

Legend: ✅ PROVEN by captured official evidence · ❌ BLOCKED/FAILED · ⚠️ UNVERIFIED (no official captured evidence; not inferred from third-party docs)

### CN_PMI

| # | Fact | Status | Evidence |
|---|---|---|---|
| 1 | Indicator identity / official name | ✅ | 中国采购经理指数（制造业采购经理指数）；release title "2026年8月中国采购经理指数运行情况 - 国家统计局"（`pmi_release_202608.html`）；table row 制造业PMI |
| 2 | Official series/code | ⚠️ | data.stats.gov.cn carries codes but API is 403-blocked → not verifiable through any accessible official channel |
| 3 | Raw value meaning / unit | ✅ | Diffusion index value (指数), unit label "单位：%" in release table; 2026-08 制造业PMI = 49.8；50 = 荣枯线 (expansion/contraction line) |
| 4 | SA/NSA | ⚠️ | Published aggregate index; SA/NSA variant flags live in the 403-blocked database and are not stated on the release page → not proven from captured official evidence |
| 5 | Observation period | ✅ | Calendar month; table covers 2025-08 … 2026-08 monthly rows |
| 6 | Release convention | ✅ | Monthly, last calendar day of month, 09:30 Beijing time |
| 7 | Historical publication timestamp | ✅ | `PubDate` meta = `2026/08/31 09:30` (exact, on-page official metadata). Conservative `available_at` = release datetime as captured; safe because the timestamp is publisher-declared in-page |
| 8 | Revision behavior | ⚠️ | No revision statement on release page; survey-based diffusion index is final-as-published, but formal revision policy is not proven from captured official evidence |
| 9 | Accessible historical depth | ❌ | Release page/attachment = rolling 13 months only; full history (since 2005) exists only in 403-blocked database |
| 10 | Machine retrieval (no auth / no bypass) | ❌→⚠️ | Current 13-month window: YES via plain HTTP (page + official `.xls` attachment). Full-history series: NO (403). Backfill would require crawling historical release pages with structure that varies across years (site was redesigned in 2023) → brittle scraper |
| 11 | Licensing / terms | ⚠️ | No explicit license text on captured pages; NBS publishes statistics publicly; no formal reuse terms captured |
| 12 | Source URL evidence | ✅ | Page `t20260831_1965154.html`; attachment `P020260831316826769515.xls`; index pages `index_10/20.html` |

### CN_CPI

| # | Fact | Status | Evidence |
|---|---|---|---|
| 1 | Indicator identity / official name | ✅ | 居民消费价格指数（全国）；release title "2026年8月份居民消费价格同比上涨0.8% - 国家统计局"（`cpi_release_202608.html`）；table 居民消费价格 |
| 2 | Official series/code | ⚠️ | Database code exists but 403-blocked → not verifiable through accessible official channel |
| 3 | Raw value meaning / unit | ⚠️ | Release gives 环比涨跌幅(%) / 同比涨跌幅(%) / 1—8月同比(%): 居民消费价格 环比0.4% 同比0.8% 1—8月0.9%. Index level (定基, e.g. 2020=100) exists only in 403-blocked database. **`config/macro.yml` keeps raw_unit=UNRESOLVED — not resolvable from this snapshot alone** |
| 4 | SA/NSA | ⚠️ | 环比/同比 both published; SA flag on 环比 is methodological knowledge, not stated on the release page → not proven from captured official evidence |
| 5 | Observation period | ✅ | Calendar month (2026年8月份) |
| 6 | Release convention | ✅ | Monthly, ~9–14th of following month, 09:30 Beijing time |
| 7 | Historical publication timestamp | ✅ | `PubDate` meta = `2026/09/09 09:30` (exact, on-page official metadata) |
| 8 | Revision behavior | ⚠️ | Base-year rebasing (2020=100) and within-series revisions are known but not evidenced on the release page → formal policy UNVERIFIED from captured official evidence |
| 9 | Accessible historical depth | ❌ | Release attachment = current-month category breakdown only (50 rows); full history only in 403-blocked database |
| 10 | Machine retrieval | ❌→⚠️ | Current-month snapshot: YES via plain HTTP (page + official `.xlsx` attachment). Historical series: NO (403); no single-page history |
| 11 | Licensing / terms | ⚠️ | No explicit license text captured (same as PMI) |
| 12 | Source URL evidence | ✅ | Page `t20260909_1965263.html`; attachment `P020260909324498220909.xlsx` |

### CN_PPI

| # | Fact | Status | Evidence |
|---|---|---|---|
| 1 | Indicator identity / official name | ✅ | 工业生产者出厂价格指数（全国）；release title "2026年8月工业生产者价格主要数据 - 国家统计局"（`ppi_release_202608.html`）；table 一、工业生产者出厂价格 |
| 2 | Official series/code | ⚠️ | Database code exists but 403-blocked → not verifiable through accessible official channel |
| 3 | Raw value meaning / unit | ⚠️ | Release gives 环比涨跌幅(%) / 同比涨跌幅(%) / 1—8月同比(%): 出厂价格 环比0.4% 同比3.8% 1—8月2.0%. **`config/macro.yml` keeps raw_unit=UNRESOLVED — not resolvable from this snapshot alone** |
| 4 | SA/NSA | ⚠️ | Same as CN_CPI — not stated on release page → not proven from captured official evidence |
| 5 | Observation period | ✅ | Calendar month (2026年8月) |
| 6 | Release convention | ✅ | Monthly, same day as CPI (~9–14th of following month, 09:30 Beijing time) |
| 7 | Historical publication timestamp | ✅ | `PubDate` meta = `2026/09/09 09:30` (exact, on-page official metadata) |
| 8 | Revision behavior | ⚠️ | Same as CN_CPI — formal policy UNVERIFIED from captured official evidence |
| 9 | Accessible historical depth | ❌ | Release attachment = current-month category breakdown only; full history only in 403-blocked database |
| 10 | Machine retrieval | ❌→⚠️ | Current-month snapshot: YES via plain HTTP (page + official `.xlsx` attachment). Historical series: NO (403) |
| 11 | Licensing / terms | ⚠️ | No explicit license text captured (same as PMI/CPI) |
| 12 | Source URL evidence | ✅ | Page `t20260909_1965262.html`; attachment `P020260909333517855845.xlsx` |

---

## Why automation is rejected (fact #10, expanded)

1. **Full-history structured route is blocked.** `data.stats.gov.cn` (the only official channel with full history, stable series codes, SA/NSA flags, index levels) returns reproducible HTTP 403. Pursuing session/cookie/JS flows would constitute the anti-bot circumvention explicitly forbidden by the Issue.
2. **The accessible channel cannot serve a durable research series.** Stats.gov.cn press releases carry only a trailing window (PMI: rolling 13 months; CPI/PPI: current month category breakdown). A research-admissible series needs real history (e.g., `min_history: 24` for normalization, plus the durable-series/PIT expectations from the existing pipeline), which the release channel cannot provide from any single stable endpoint.
3. **Backfill would be a brittle scraper.** Reconstructing history means crawling ~200+ monthly release pages across years of differing HTML structure (the site was redesigned in 2023; pre-2023 releases use a different layout). This is precisely the "brittle scraper" the Issue says not to build.
4. **CN_CPI / CN_PPI semantics are unresolvable at this stage.** `config/macro.yml` marks both `raw_unit`/`derived_unit` as `UNRESOLVED`; Issue #103 forbids resolving them merely because values can be downloaded. Only CN_PMI has resolved semantics (index level, 50 baseline), but its durable-history route is blocked as above.

## Recommendation

Keep **CN_PMI / CN_CPI / CN_PPI on Lane B (manual export)** via the existing Issue #93 `manual_intake` path. The verified official facts (identity, units, release schedule, exact `PubDate` timestamps) are now captured for when a user supplies official NBS export files; they can also inform any future WEB-CONTROL decision on resolving CN_CPI/CN_PPI semantics, which must cite official source evidence and remain subject to review.

## Remaining blockers

- `NBS_DB_HTTP_403`: data.stats.gov.cn API unreachable via plain HTTP (UrlACL) — full history, series codes, SA flags, index levels unavailable.
- `RELEASE_WINDOW_ONLY`: stats.gov.cn releases carry only trailing windows (PMI 13 months; CPI/PPI current month) — insufficient for durable backfill without brittle scraping.
- `CN_CPI_SEMANTICS_UNRESOLVED` / `CN_PPI_SEMANTICS_UNRESOLVED`: `config/macro.yml` raw units unresolved; not resolvable from a downloadable snapshot alone.
- `CN_PMI_HISTORY_UNAVAILABLE`: forward collection is feasible (official attachment via HTTP) but a durable historical series cannot be built from the stable official route today.
