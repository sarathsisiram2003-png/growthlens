"""CLI: python -m growthlens.cli run --city Bengaluru --category cafe"""
from pathlib import Path

import typer

from .pipeline import run_pipeline, save_result

app = typer.Typer(add_completion=False, help="GrowthLens pipeline")


@app.command()
def run(
    city: str = typer.Option("Bengaluru", help="City name"),
    category: str = typer.Option("cafe", help="Business category profile"),
    out: Path | None = typer.Option(None, help="Output JSON path"),
    skip_satellite: bool = typer.Option(False, help="Skip Earth Engine (OSM-only dry run)"),
) -> None:
    result = run_pipeline(city, category, progress=typer.echo, skip_satellite=skip_satellite)
    path = save_result(result, out)
    typer.echo(f"\nWrote {path}")
    typer.echo(f"Data-quality flags: {result['data_quality']['flags'] or 'none'}")
    typer.echo("\nTop 10 areas:")
    by_hex = {h["hex"]: h for h in result["hexes"]}
    for i, c in enumerate(result["top10"], 1):
        h = by_hex[c]
        typer.echo(f"  {i:>2}. {c}  score {h['score']:5.1f}  ({h['lat']}, {h['lon']})")


if __name__ == "__main__":
    app()
