"""Bootstrap for the real-Home-Assistant guard suite.

Unlike ``tests/`` (which stubs HA so pure logic runs without it), this suite
installs Home Assistant and ``pytest-homeassistant-custom-component`` so it can
catch bugs the stubbed suite cannot: wrong ``homeassistant.*`` imports and
invalid selector/flow schemas that only fail against the real framework.

Run it on its own (``pytest tests_ha``) so the ``tests/`` stub never applies.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# pytest puts this file's dir (tests_ha/) on sys.path, not the repo root, so
# ``import custom_components.swelligence`` would fail. Add the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make Home Assistant load custom_components/swelligence in every test."""
    yield
