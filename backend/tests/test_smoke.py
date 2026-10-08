from hypothesis import settings


def test_package_imports():
    import agentwatch_api
    import agentwatch_api.handlers  # noqa: F401

    assert agentwatch_api is not None


def test_hypothesis_ci_profile_loaded():
    assert settings().max_examples == 100
    assert settings.get_profile("ci").max_examples == 100
