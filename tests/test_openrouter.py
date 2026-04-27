from company_mcp.models import openrouter


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
