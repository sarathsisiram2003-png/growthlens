import json

import pytest

from growthlens import satellite as sat
from growthlens.config import settings

KEY = json.dumps({"client_email": "svc@proj.iam.gserviceaccount.com", "private_key": "x", "type": "service_account"})


@pytest.fixture
def fake_ee(monkeypatch):
    calls = {}
    monkeypatch.setattr(sat, "_initialised", False)
    monkeypatch.setattr(settings, "ee_project", "my-project")
    monkeypatch.setattr(settings, "ee_service_account_json", "")
    monkeypatch.setattr(settings, "ee_service_account_key", "")
    monkeypatch.setattr(settings, "ee_service_account_email", "")

    def creds(email, key_file=None, key_data=None):
        calls["creds"] = (email, key_file, key_data)
        return "CREDS"

    def initialize(c=None, project=None):
        calls["init"] = (c, project)

    monkeypatch.setattr(sat.ee, "ServiceAccountCredentials", creds)
    monkeypatch.setattr(sat.ee, "Initialize", initialize)
    monkeypatch.setattr(sat.ee.data, "setDeadline", lambda ms: calls.__setitem__("deadline", ms))
    return calls


def test_key_json_from_environment_is_used_without_touching_disk(fake_ee, monkeypatch):
    monkeypatch.setattr(settings, "ee_service_account_json", KEY)
    sat.init_ee()
    assert fake_ee["creds"] == ("svc@proj.iam.gserviceaccount.com", None, KEY)
    assert fake_ee["init"] == ("CREDS", "my-project")


def test_key_file_still_works(fake_ee, monkeypatch):
    monkeypatch.setattr(settings, "ee_service_account_key", "key.json")
    monkeypatch.setattr(settings, "ee_service_account_email", "a@b.iam")
    sat.init_ee()
    assert fake_ee["creds"] == ("a@b.iam", "key.json", None)


def test_falls_back_to_user_login(fake_ee):
    sat.init_ee()
    assert fake_ee["init"] == (None, "my-project")  # no explicit credentials: the cached user login is used
    assert "creds" not in fake_ee


def test_missing_project_is_a_clear_error(fake_ee, monkeypatch):
    monkeypatch.setattr(settings, "ee_project", "")
    with pytest.raises(sat.EarthEngineError, match="EE_PROJECT"):
        sat.init_ee()


def test_bad_key_json_is_reported_not_crashed(fake_ee, monkeypatch):
    monkeypatch.setattr(settings, "ee_service_account_json", "not json")
    with pytest.raises(sat.EarthEngineError, match="Earth Engine init failed"):
        sat.init_ee()


def test_init_runs_once(fake_ee, monkeypatch):
    monkeypatch.setattr(settings, "ee_service_account_json", KEY)
    sat.init_ee()
    fake_ee.clear()
    sat.init_ee()
    assert fake_ee == {}  # second call did nothing


def test_a_request_deadline_is_set(fake_ee):
    sat.init_ee()
    assert fake_ee["deadline"] == sat.EE_REQUEST_DEADLINE_MS
