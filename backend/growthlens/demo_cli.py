"""Build a demo pack: python -m growthlens.demo_cli --city "Dubai, United Arab Emirates" --slug dubai

Needs the live data sources once (Nominatim, Overpass, Earth Engine, optionally Gemini); the pack it writes to
backend/demo/<slug>/ is then served with none of them. Uses the preset business profile so demos are deterministic.
"""
import json
import shutil
import sys
from datetime import datetime, timezone

import typer

from . import demo, history
from .brief import build_brief
from .config import settings
from .imagery import no_data_marker, thumbnail_png
from .intent import intent_from_preset
from .jobs import result_path
from .pipeline import run_pipeline, save_result

app = typer.Typer(add_completion=False, help="Pre-computed demo cities")
DEFAULT_QUERY = "A specialty café for college students"


@app.command()
def build(
    city: str = typer.Option(..., help='Full place name, e.g. "Dubai, United Arab Emirates"'),
    slug: str = typer.Option(..., help="Folder / URL name, e.g. dubai"),
    label: str = typer.Option("", help="Display name (default: first part of the city)"),
    skip_imagery: bool = typer.Option(False, help="Do not fetch before/after satellite images"),
    skip_history: bool = typer.Option(False, help="Do not compute the growth-replay history"),
    brief_retries: int = typer.Option(3, help="Tries per brief to get an AI-written one before accepting a template"),
) -> None:
    # Area names can be in any script (Arabic, Japanese, ...); never let a console encoding crash a long build
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    intent = intent_from_preset("cafe")
    typer.echo(f"1/5 Running the pipeline for {city}")
    result = run_pipeline(city, intent, progress=lambda _s, m, _meta=None: typer.echo(f"    {m}"))
    path = result_path(city, intent.model_dump(), intent.category_key)
    save_result(result, path)
    rid = path.stem
    pack = demo.pack_dir(slug)
    shutil.copyfile(path, pack / "result.json")
    by_hex = {h["hex"]: h for h in result["hexes"]}
    top = [by_hex[h] for h in result["top10"]]
    typer.echo(f"    {len(result['hexes'])} areas, data quality: {result['data_quality']['level']}")

    typer.echo("2/5 Growth history for the replay slider")
    if skip_history:
        typer.echo("    skipped")
    else:
        history._state[rid] = {"state": "running", "progress": 0.0}
        history._compute(rid)
        if history._state[rid]["state"] != "done":
            raise typer.Exit(f"history failed: {history._state[rid].get('error')}")
        shutil.copyfile(settings.cache_dir / "history" / f"{rid}.json", pack / "history.json")

    typer.echo("3/5 Location briefs for the top 10")
    briefs: dict[str, dict] = {}
    for row in top:
        best = None
        for _ in range(brief_retries):
            b = build_brief(result, row)
            best = b
            if b.source == "llm":
                break
        briefs[row["hex"]] = best.model_dump()
        typer.echo(f"    #{row['rank']} {row.get('name')}: {best.source}")
    (pack / "briefs.json").write_text(json.dumps(briefs, ensure_ascii=False, indent=1), encoding="utf-8")

    typer.echo("4/5 Before/after satellite images for the top 10")
    if skip_imagery:
        typer.echo("    skipped")
    else:
        img_dir = pack / "imagery"
        img_dir.mkdir(exist_ok=True)
        before, after = result["windows"]["imagery"]
        for row in top:
            # The drawer falls back to up to 2 years later when the earliest year has no usable scenes (mirror that here)
            for y in [before, before + 1, before + 2, after]:
                if y != after and y != before and (img_dir / f"{row['hex']}_{before}.png").exists():
                    continue  # the first choice worked; no fallback needed
                if y == before + 2 and (img_dir / f"{row['hex']}_{before + 1}.png").exists():
                    continue
                try:
                    (img_dir / f"{row['hex']}_{y}.png").write_bytes(thumbnail_png(row["hex"], y))
                except Exception as e:  # noqa: BLE001 - a missing image just means that view loads live
                    typer.echo(f"    ! {row['hex']} {y}: {e}")
                    marker = no_data_marker(row["hex"], y)
                    if marker.exists():  # ship the definite answer so the demo falls back to a later year instantly
                        shutil.copyfile(marker, img_dir / marker.name)

    typer.echo("5/5 Updating the demo index")
    entries = [e for e in demo.index() if e["slug"] != slug]
    entries.append({
        "slug": slug, "city": city, "label": label or city.split(",")[0], "result_id": rid, "query": DEFAULT_QUERY,
        "n_areas": len(result["hexes"]), "data_quality": result["data_quality"]["level"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    demo.write_index(sorted(entries, key=lambda e: e["label"]))
    size = sum(f.stat().st_size for f in pack.rglob("*") if f.is_file()) / 1e6
    typer.echo(f"\nDone: backend/demo/{slug}/ ({size:.1f} MB)")


if __name__ == "__main__":
    app()
