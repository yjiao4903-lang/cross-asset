# LIVE_CORE_8 Requirements v0.1

`LIVE_CORE_8` is an engineering coverage target, not a homogeneous research core and not a `DATA_READY` declaration. Owner: TBD; reviewer: TBD; approved at: TBD.

| Series | Primary candidate | Auxiliary/禁用 | Canonical requirements | Current classification |
|---|---|---|---|---|
| US_EQ | Yahoo `^GSPC` candidate | none approved | daily index, USD; price/total-return, adjustment, close cutoff, PIT and permission required | UNRESOLVED_ENTITLEMENT_AND_PIT |
| GOLD | Yahoo `GC=F` candidate | none approved | daily futures price, USD; contract/roll/adjustment/PIT required | UNRESOLVED_ENTITLEMENT_AND_PIT |
| COPPER | Yahoo `HG=F` candidate | none approved | daily futures price, USD; contract/roll/adjustment/PIT required | UNRESOLVED_ENTITLEMENT_AND_PIT |
| DXY | Yahoo `DX-Y.NYB` candidate | none approved | daily index points, USD; definition/cutoff/PIT required | UNRESOLVED_ENTITLEMENT_AND_PIT |
| US_GOV_10Y | FRED DGS10 | Yahoo `^TNX` auxiliary only | daily yield %, USD; realtime/vintage, terms, permission and PIT run required | TECHNICALLY_SUPPORTED_TERMS_PENDING |
| US_REAL_10Y | FRED DFII10 | none approved | daily real yield %, USD; realtime/vintage, terms, permission and PIT run required | TECHNICALLY_SUPPORTED_TERMS_PENDING |

2026-08-31 offline/public-CSV evidence: FRED public graph CSV returned DGS10/DFII10 samples (693 rows each, 2024-01-02 to 2026-08-27) with stable repeat hashes. This verifies transport/raw shape only; no first-release `available_at`, so both remain blocked for formal PIT acceptance.
| CN_EQ_LARGE | SSE/CSI/Wind/iFinD candidate | no unapproved proxy | daily index points, CNY; exact code, price type, permission, calendar/PIT required | NEEDS_USER_EXPORT |
| CN_EQ_SMALL | SSE/CSI/Wind/iFinD candidate | no unapproved proxy | daily index points, CNY; exact code, price type, permission, calendar/PIT required | NEEDS_USER_EXPORT |

Admission fields for every row: `semantic_equivalence`, `price_type`, `adjustment_type`, `close_cutoff_timezone`, `available_at_rule`, `permission_scope`, `history_start/end`, `repeatability_evidence`, plus manifest reviewer/approval. All classifications are candidates only; project remains `DATA_BLOCKED`.
