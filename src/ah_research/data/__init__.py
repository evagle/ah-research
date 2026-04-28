"""Data layer: cache, converters, repository, curated data files.

Composition order, bottom-up:

 1. ``cache.py`` — DuckDB-backed storage, owns migrations and raw IO.
 2. ``converters.py`` — pure functions source-shape → domain-shape.
 3. ``repository.py`` — DataRepository DI's sources + cache, enforces PIT.
 4. ``ah_pairs.py`` — loader for the curated ``ah_pairs.yaml``.
"""
