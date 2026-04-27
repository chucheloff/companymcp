from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayCaseResult:
    case_id: str
    elapsed_seconds: float
    company_profile_confidence: float
    news_items: int
    interviewer_confidence: float | None = None
    useful: bool = True


@dataclass(frozen=True)
class ReplaySummary:
    total_cases: int
    successful_cases: int
    success_rate: float
    target_rate: float
    passes_target: bool


def evaluate_replay_results(
    results: list[ReplayCaseResult],
    *,
    target_rate: float = 0.8,
    max_seconds: float = 600.0,
    min_profile_confidence: float = 0.45,
) -> ReplaySummary:
    successful = [
        result
        for result in results
        if result.useful
        and result.elapsed_seconds <= max_seconds
        and result.company_profile_confidence >= min_profile_confidence
        and result.news_items >= 0
    ]
    success_rate = len(successful) / len(results) if results else 0.0
    return ReplaySummary(
        total_cases=len(results),
        successful_cases=len(successful),
        success_rate=success_rate,
        target_rate=target_rate,
        passes_target=success_rate >= target_rate,
    )
