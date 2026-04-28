"""Deterministic fake sources for tests.

Exposes a single ``FakeSources`` dataclass whose attributes are concrete
implementations of every Protocol in ``integrations._protocols``. Use this
in ``tests/conftest.py`` fixtures to exercise the repository and converter
layers without a network.
"""

from ah_research.integrations.fake.client import FakeSources

__all__ = ["FakeSources"]
