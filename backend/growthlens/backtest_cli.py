"""CLI: python -m growthlens.backtest_cli --out ../docs/backtest.json  (needs Earth Engine; reruns use the cache)"""
from pathlib import Path

import typer

from .backtest import DEFAULT_CITIES, Config, markdown_table, run

app = typer.Typer(add_completion=False, help="Backtest the satellite growth signal")


@app.command()
def main(
    city: list[str] = typer.Option(None, "--city", help="City to include (repeatable). Default: the standard set."),
    out: Path = typer.Option(Path("../docs/backtest.json"), help="Where to write the JSON report"),
    t0: int = typer.Option(2020, help="'As of' year: only data up to this year feeds the score"),
    end: int = typer.Option(2025, help="Last year of the outcome window"),
    sensitivity: bool = typer.Option(True, help="Also run the gap-year sensitivity analysis (uses cached satellite data)"),
) -> None:
    cfg = Config(t0=t0, future_end=end)
    # Gap-year design: score on one year less of history and measure the outcome from the year AFTER t0,
    # so the signal and the outcome share no year.
    sens_cfg = Config(t0=t0 - 1, outcome_start=t0 + 1, future_end=end) if sensitivity else None
    report = run(city or DEFAULT_CITIES, cfg, out, say=typer.echo, sensitivity=sens_cfg)
    typer.echo(f"\nWrote {out}\n")
    typer.echo(markdown_table(report))


if __name__ == "__main__":
    app()
