import pytest

from growthlens import ratelimit
from growthlens.config import settings


@pytest.fixture(autouse=True)
def _no_rate_limits_by_default(monkeypatch):
    """Tests hit the API far more often than a real client; the rate-limit tests turn this back on."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    ratelimit.reset()
    yield
    ratelimit.reset()
