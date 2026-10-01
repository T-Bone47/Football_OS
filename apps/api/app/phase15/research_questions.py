"""Research Questions Registry for Phase 15.

Manages top-level research inquiries that frame hypotheses, experiments, and validations.
"""

from app.phase15.research_models import ResearchQuestion


class ResearchQuestionRegistry:
    """Manages institutional research inquiries and problem statements."""

    def __init__(self) -> None:
        self._questions: dict[str, ResearchQuestion] = {}

    def create_question(
        self,
        question_id: str,
        title: str,
        description: str,
        tags: list[str] | None = None,
        competition_scope: list[str] | None = None,
    ) -> ResearchQuestion:
        q = ResearchQuestion(
            research_id=f"res_{question_id}",
            question_id=question_id,
            title=title,
            description=description,
            tags=tags or [],
            competition_scope=competition_scope or ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"],
        )
        self._questions[question_id] = q
        return q

    def get_question(self, question_id: str) -> ResearchQuestion:
        if question_id not in self._questions:
            raise KeyError(f"ResearchQuestion '{question_id}' not found.")
        return self._questions[question_id]

    def list_questions(self) -> list[ResearchQuestion]:
        return list(self._questions.values())


_GLOBAL_QUESTION_REGISTRY: ResearchQuestionRegistry | None = None


def get_question_registry() -> ResearchQuestionRegistry:
    global _GLOBAL_QUESTION_REGISTRY
    if _GLOBAL_QUESTION_REGISTRY is None:
        _GLOBAL_QUESTION_REGISTRY = ResearchQuestionRegistry()
        _GLOBAL_QUESTION_REGISTRY.create_question(
            question_id="rq_001_league_adaptation",
            title="What factors characterize successful cross-league adaptation from Bundesliga to EPL?",
            description="Empirical investigation into contribution translation, minutes sustainability, and physical adaptation profiles.",
            tags=["recruitment", "league_translation", "bundesliga", "epl"],
        )
        _GLOBAL_QUESTION_REGISTRY.create_question(
            question_id="rq_002_role_transition_retention",
            title="How reliably do inverted fullbacks retain ball progression capacity in tier-1 transitions?",
            description="Analysis of positional shifts into midfield pivots across symmetric and asymmetric structures.",
            tags=["tactical", "role_transition", "ball_progression"],
        )
    return _GLOBAL_QUESTION_REGISTRY
