"""CLI: python -m growthlens.cli run --city Bengaluru --query "specialty café for college students" """
from pathlib import Path

import typer

from .intent import parse_intent
from .pipeline import run_pipeline, save_result

app = typer.Typer(add_completion=False, help="GrowthLens pipeline")


@app.command()
def run(
    city: str = typer.Option("Bengaluru", help="City name"),
    query: str = typer.Option("cafe", help="What you want to open, in plain words"),
    out: Path | None = typer.Option(None, help="Output JSON path"),
    skip_satellite: bool = typer.Option(False, help="Skip Earth Engine (OSM-only dry run)"),
    no_llm: bool = typer.Option(False, help="Do not call the LLM; use keyword-matched presets"),
) -> None:
    intent, warning = parse_intent(query, use_llm=not no_llm)
    if warning:
        typer.secho(f"! {warning}", fg=typer.colors.YELLOW)
    typer.echo(f"Understood: {intent.label} [{intent.source}] - {intent.summary}")
    typer.echo(f"  Competitors: {', '.join(f'{t.key}={t.value or '*'}' for t in intent.competitors)}")
    typer.echo(f"  Demand: {', '.join(f'{d.key}={d.value or '*'}({d.weight:g})' for d in intent.demand_drivers)}")
    typer.echo(f"  Weights: {intent.to_profile()['weights']}\n")

    result = run_pipeline(city, intent, progress=typer.echo, skip_satellite=skip_satellite)
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
