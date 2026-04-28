from company_mcp.models import openrouter


def test_default_openrouter_models_are_current_openai_slugs() -> None:
    assert openrouter.settings.openrouter_extraction_model == "openai/gpt-5-mini"
    assert openrouter.settings.openrouter_quality_model == "openai/gpt-5.1"


def test_model_for_task_routes_light_tasks_to_extraction_model(monkeypatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_extraction_model", "light-model")
    monkeypatch.setattr(openrouter.settings, "openrouter_quality_model", "heavy-model")

    assert openrouter.model_for_task("company_profile_extract") == "light-model"
    assert openrouter.model_for_task("linkedin_lookup") == "light-model"
    assert openrouter.model_for_task("news_summary") == "light-model"


def test_model_for_task_routes_brief_tasks_to_quality_model(monkeypatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_extraction_model", "light-model")
    monkeypatch.setattr(openrouter.settings, "openrouter_quality_model", "heavy-model")

    assert openrouter.model_for_task("final_brief") == "heavy-model"
    assert openrouter.model_for_task("quality_synthesis") == "heavy-model"


def test_max_tokens_for_task_caps_openrouter_reservations() -> None:
    assert openrouter.max_tokens_for_task("news_summary") == 350
    assert openrouter.max_tokens_for_task("linkedin_lookup") == 900
    assert openrouter.max_tokens_for_task("company_profile_extract") == 1200
    assert openrouter.max_tokens_for_task("final_brief") == 2000
    assert openrouter.max_tokens_for_task("quality_synthesis") == 2000
