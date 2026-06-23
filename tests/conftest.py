"""Test bootstrap.

The pure logic under test (scoring, sports, policy, provider normalisation) has
no Home Assistant dependency, but the package ``__init__`` imports homeassistant.
We register a lightweight stub ``swelligence`` package pointing at the source
dir so ``from swelligence.scoring import ...`` resolves the pure submodules
without pulling in (or installing) Home Assistant. Config-flow/coordinator tests
that genuinely need HA belong in the live-HA harness, tracked separately.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "swelligence"

if "swelligence" not in sys.modules:
    _pkg = types.ModuleType("swelligence")
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["swelligence"] = _pkg
