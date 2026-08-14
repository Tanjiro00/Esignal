from pydantic import SecretStr

from apps.api.config import Settings


def test_improvement_feature_flags_default_to_off() -> None:
    flags = Settings(_env_file=None).improvement_features.as_dict()

    assert flags
    assert all(enabled is False for enabled in flags.values())


def test_improvement_feature_flags_are_independently_configurable() -> None:
    settings = Settings(
        _env_file=None,
        feature_earlyness_timeline=True,
        feature_signal_packaging=True,
    )

    assert settings.improvement_features.earlyness_timeline is True
    assert settings.improvement_features.signal_packaging is True
    assert settings.improvement_features.signal_review_queue is False


def test_development_allows_local_web_origins() -> None:
    settings = Settings(_env_file=None, web_origin="http://localhost:3000")

    assert settings.allowed_web_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_production_allows_only_the_configured_web_origin() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        web_origin="https://esignal.tech",
    )

    assert settings.allowed_web_origins == ["https://esignal.tech"]


def test_production_runtime_validation_fails_closed() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        demo_mode=False,
        web_origin="https://esignal.tech",
        auth_required=True,
        auth_cookie_secure=True,
        auth_pepper=SecretStr(""),
    )

    try:
        settings.validate_runtime()
    except ValueError as error:
        assert "AUTH_PEPPER is required" in str(error)
    else:
        raise AssertionError("unsafe production settings must fail validation")


def test_secure_production_runtime_configuration_is_accepted() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        demo_mode=False,
        web_origin="https://esignal.tech",
        auth_required=True,
        auth_cookie_secure=True,
        auth_pepper=SecretStr("pepper"),
    )

    settings.validate_runtime()
