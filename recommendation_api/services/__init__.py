from typing import Optional
from . import recommender
from . import collaborative
from . import content_based
from . import hotness
from .recommender import RecommendationEngine

_engine: Optional[RecommendationEngine] = None


def get_engine() -> Optional[RecommendationEngine]:
    return _engine


def set_engine(engine: RecommendationEngine) -> None:
    global _engine
    _engine = engine


__all__ = [
    "recommender",
    "collaborative",
    "content_based",
    "hotness",
    "RecommendationEngine",
    "get_engine",
    "set_engine",
]
