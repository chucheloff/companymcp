from company_mcp.models import openrouter


def test_default_openrouter_models_are_current_openai_slugs() -> None:
    assert openrouter.settings.openrouter_model_tier == "free"
    assert openrouter.settings.openrouter_free_extraction_model == "openrouter/free"
    assert openrouter.settings.openrouter_free_quality_model == "openrouter/free"
    assert openrouter.settings.openrouter_extraction_model == "openai/gpt-5-mini"
    assert openrouter.settings.openrouter_quality_model == "openai/gpt-5.1"


def test_model_for_task_routes_free_tier_to_free_models(monkeypatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_model_tier", "free")
    monkeypatch.setattr(openrouter.settings, "openrouter_free_extraction_model", "free-light")
    monkeypatch.setattr(openrouter.settings, "openrouter_free_quality_model", "free-heavy")
    monkeypatch.setattr(openrouter.settings, "openrouter_extraction_model", "paid-light")
    monkeypatch.setattr(openrouter.settings, "openrouter_quality_model", "paid-heavy")

    assert openrouter.model_for_task("company_profile_extract") == "free-light"
    assert openrouter.model_for_task("linkedin_lookup") == "free-light"
    assert openrouter.model_for_task("news_summary") == "free-light"
    assert openrouter.model_for_task("final_brief") == "free-heavy"
    assert openrouter.model_for_task("quality_synthesis") == "free-heavy"


def test_model_for_task_routes_paid_tier_to_paid_models(monkeypatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_model_tier", "paid")
    monkeypatch.setattr(openrouter.settings, "openrouter_free_extraction_model", "free-light")
    monkeypatch.setattr(openrouter.settings, "openrouter_free_quality_model", "free-heavy")
    monkeypatch.setattr(openrouter.settings, "openrouter_extraction_model", "light-model")
    monkeypatch.setattr(openrouter.settings, "openrouter_quality_model", "heavy-model")

    assert openrouter.model_for_task("company_profile_extract") == "light-model"
    assert openrouter.model_for_task("linkedin_lookup") == "light-model"
    assert openrouter.model_for_task("news_summary") == "light-model"
    assert openrouter.model_for_task("final_brief") == "heavy-model"
    assert openrouter.model_for_task("quality_synthesis") == "heavy-model"


def test_model_for_task_defaults_unknown_tier_to_free(monkeypatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_model_tier", "unexpected")
    monkeypatch.setattr(openrouter.settings, "openrouter_free_extraction_model", "free-light")

    assert openrouter.model_for_task("news_summary") == "free-light"


def test_max_tokens_for_task_caps_openrouter_reservations() -> None:
    assert openrouter.max_tokens_for_task("news_summary") == 350
    assert openrouter.max_tokens_for_task("linkedin_lookup") == 900
    assert openrouter.max_tokens_for_task("company_profile_extract") == 1200
    assert openrouter.max_tokens_for_task("final_brief") == 2000
    assert openrouter.max_tokens_for_task("quality_synthesis") == 2000
