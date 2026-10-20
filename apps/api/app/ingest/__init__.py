"""Ingest real open data and news from public sources (docs/features.md F-01 / F-08).

Run: python -m app.ingest [datasets|news|all]
Every run is recorded in ingest_runs, including sources that could not be
fetched; nothing is filled in with made-up values when a source fails.
"""
