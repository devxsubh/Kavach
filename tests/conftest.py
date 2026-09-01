import pytest


@pytest.fixture(autouse=True)
def skip_dotenv_for_tests(monkeypatch):
    monkeypatch.setenv("KAVACH_SKIP_DOTENV", "1")
    import kavach.config as config_module

    config_module._ENV_LOADED = False
    yield
    config_module._ENV_LOADED = False
