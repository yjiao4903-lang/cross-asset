from pathlib import Path


def generate_daily_report(
    *,
    output="artifacts/reports/daily.md",
    market=None,
    macro=None,
    style=None,
    assets=None,
    allocation=None,
    contributions=None,
    conflicts=None,
    data_health=None,
    as_of=None,
    model_version="market_v0.1",
    data_cutoff=None,
    offline_fixture=False,
):
    text = f"# Daily Allocation Report\n\n- as_of: {as_of}\n- model_version: {model_version}\n- data_cutoff: {data_cutoff}\n- source: {'offline fixture' if offline_fixture else 'configured providers'}\n\n"
    for name, value in [
        ("Market", market),
        ("Macro", macro),
        ("Style", style),
        ("Asset", assets),
        ("Allocation", allocation),
        ("Contributions", contributions),
        ("Signal Conflicts", conflicts),
        ("Data Health", data_health),
    ]:
        text += f"## {name}\n\n{value!r}\n\n"
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p
