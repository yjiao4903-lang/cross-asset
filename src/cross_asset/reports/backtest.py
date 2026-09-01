from pathlib import Path


def generate_backtest_report(
    results: dict, *, output="artifacts/reports/backtest.md", offline_fixture=True, assumptions=None
):
    lines = [
        "# Backtest Comparison Report",
        "",
        f"Source: {'offline fixture' if offline_fixture else 'configured data'}",
        "",
        "Research assumptions:",
    ]
    for item in assumptions or [
        "deterministic weekly rebalance",
        "next-period effective",
        "cost_bps is a research placeholder",
        "no random shuffle",
    ]:
        lines.append(f"- {item}")
    lines += [
        "",
        "| Model | CAGR | Sharpe | Max drawdown | Turnover |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, data in results.items():
        m = data.get("net", data)
        lines.append(
            f"| {model} | {m.get('CAGR')} | {m.get('Sharpe')} | {m.get('max_drawdown')} | {m.get('turnover')} |"
        )
    lines += ["", "## Full metrics", "", repr(results)]
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
