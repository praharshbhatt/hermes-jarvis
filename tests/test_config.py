import pytest

from hermes_jarvis import config
from hermes_jarvis.errors import UserError


def test_defaults_are_generic():
    c = config.use()
    assert c.brain.type == "hermes" and c.persona == "jarvis" and c.admin.host == "127.0.0.1"
    assert c.device.host == "" and c.privacy.save_recordings is False


def test_yaml_overrides_defaults_and_unknown_keys_are_rejected(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("brain:\n  type: openai\n  model: llama3.1\nadmin:\n  port: 9000\n")
    c = config.load(f)
    assert c.brain.type == "openai" and c.brain.model == "llama3.1" and c.admin.port == 9000
    assert c.brain.base_url == "http://localhost:8642"  # untouched defaults survive
    f.write_text("braiin:\n  type: openai\n")
    with pytest.raises(UserError, match="unknown config key"):
        config.load(f)


def test_environment_overrides_with_types(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("admin:\n  port: 9000\n")
    monkeypatch.setenv("HJ_ADMIN_PORT", "9100")
    monkeypatch.setenv("HJ_ADMIN_HOST", "0.0.0.0")
    monkeypatch.setenv("HJ_PRIVACY_SAVE_RECORDINGS", "true")
    c = config.load(f)
    assert c.admin.port == 9100 and c.admin.host == "0.0.0.0" and c.privacy.save_recordings is True


def test_dotenv_is_read_but_never_overrides_the_environment(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("")
    (tmp_path / ".env").write_text("# c\nSOME_KEY=from-file\nOTHER_KEY='quoted'\nexport EXPORTED=yes\n")
    monkeypatch.setenv("OTHER_KEY", "from-env")
    monkeypatch.delenv("SOME_KEY", raising=False)
    config.load(tmp_path / "config.yaml")
    assert config.secret("SOME_KEY") == "from-file"
    assert config.secret("OTHER_KEY") == "from-env"
    assert config.secret("EXPORTED") == "yes"


def test_data_path_is_relative_to_the_config_file(tmp_path):
    (tmp_path / "config.yaml").write_text("data_dir: ./state\n")
    c = config.load(tmp_path / "config.yaml")
    assert c.data_path("x.json") == (tmp_path / "state" / "x.json").resolve()


def test_device_key_and_host_precedence(monkeypatch):
    assert config.device_key() is None and config.device_host() == ""
    config.save_device({"host": "10.0.0.5", "name": "voice-1", "key": "saved-key"})
    assert config.device_key() == "saved-key" and config.device_host() == "10.0.0.5"
    monkeypatch.setenv("ESPHOME_API_KEY", "env-key")
    assert config.device_key() == "env-key"
    config.use({"device": {"host": "10.0.0.9"}, "data_dir": str(config.cfg.data_path())})
    assert config.device_host() == "10.0.0.9"
    assert oct(config.cfg.data_path("device.json").stat().st_mode & 0o777) == "0o600"  # the key file is private


def test_lan_ip_honours_public_host():
    config.use({"audio": {"public_host": "192.168.1.50"}})
    assert config.lan_ip() == "192.168.1.50"


def test_an_explicit_config_path_must_exist(tmp_path):
    with pytest.raises(UserError, match="config file not found"):
        config.load(tmp_path / "nope.yaml")


def test_a_missing_default_config_is_fine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no ./config.yaml here: run on defaults
    assert config.load().brain.type == "hermes"


def test_a_bad_number_in_the_environment_says_which_variable(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("")
    monkeypatch.setenv("HJ_DEVICE_PORT", "sixty")
    with pytest.raises(UserError, match="HJ_DEVICE_PORT"):
        config.load(tmp_path / "config.yaml")


def test_misspelled_environment_settings_are_reported(tmp_path, monkeypatch, caplog):
    (tmp_path / "config.yaml").write_text("")
    monkeypatch.setenv("HJ_ADMN_PORT", "9000")
    with caplog.at_level("WARNING"):
        config.load(tmp_path / "config.yaml")
    assert "HJ_ADMN_PORT" in caplog.text
