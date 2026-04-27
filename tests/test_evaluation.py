from company_mcp.evaluation import ReplayCaseResult, evaluate_replay_results


def test_replay_success_rate_uses_probabilistic_target() -> None:
    results = [
        ReplayCaseResult(
            case_id=str(index),
            elapsed_seconds=120,
            company_profile_confidence=0.6,
            news_items=2,
        )
        for index in range(8)
    ] + [
        ReplayCaseResult(
            case_id="slow",
            elapsed_seconds=900,
            company_profile_confidence=0.6,
            news_items=2,
        ),
        ReplayCaseResult(
            case_id="weak",
            elapsed_seconds=120,
            company_profile_confidence=0.2,
            news_items=2,
        ),
    ]

    summary = evaluate_replay_results(results)

    assert summary.success_rate == 0.8
    assert summary.passes_target is True
