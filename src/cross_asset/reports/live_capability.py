import json
from datetime import UTC, datetime
from pathlib import Path


def write_live_capability(records, output_dir="artifacts/live"):
    stamp=datetime.now(UTC).strftime("%Y%m%d"); out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    jp=out/f"provider_capability_{stamp}.json"; mp=out/f"provider_capability_{stamp}.md"; jp.write_text(json.dumps({"providers":records},ensure_ascii=False,indent=2),encoding="utf-8")
    fields=["provider","authenticated","reachable","historical_query","latest_query","latency_ms","earliest_date","latest_date","quota_info_if_available","error_type","safe_error","verified_at"]
    text=["# Live Provider Capability", "", "Opt-in network probe; secrets are omitted.", "", "|"+"|".join(fields)+"|", "|"+"|".join(["---"]*len(fields))+"|"]
    text += ["|"+"|".join(str(r.get(f,"")).replace("|","/") for f in fields)+"|" for r in records]; mp.write_text("\n".join(text)+"\n",encoding="utf-8"); return jp,mp
