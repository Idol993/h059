import time
import math
from typing import List, Dict, Any, Tuple
from functools import lru_cache
from .config import settings


def time_decay_score(
    likes: int,
    comments: int,
    created_at: int,
    current_time: int = None,
    gravity: float = 1.5,
) -> float:
    if current_time is None:
        current_time = int(time.time())

    time_diff_seconds = current_time - created_at
    time_diff_hours = time_diff_seconds / 3600.0

    score = (likes + comments * 2) / math.pow(time_diff_hours + 2, gravity)
    return score


def min_max_normalize(scores: List[float]) -> List[float]:
    if not scores:
        return []

    min_score = min(scores)
    max_score = max(scores)

    if max_score == min_score:
        return [0.5 for _ in scores]

    return [(s - min_score) / (max_score - min_score) for s in scores]


def z_score_normalize(scores: List[float]) -> List[float]:
    if not scores:
        return []

    import numpy as np
    mean = np.mean(scores)
    std = np.std(scores)

    if std == 0:
        return [0.5 for _ in scores]

    return [(s - mean) / std for s in scores]


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def get_item_cache_key(item_id: int) -> str:
    return f"item:{item_id}:features"


def get_recommend_cache_key(user_id: int, strategy: str, ab_group: str) -> str:
    return f"rec:{user_id}:{strategy}:{ab_group}"


def get_user_profile_key(user_id: int) -> str:
    return f"user:{user_id}:profile"


def get_ab_config_key(group: str) -> str:
    return f"ab_config:{group}"


def get_train_counter_key() -> str:
    return "train:new_behaviors_count"


def get_last_train_time_key() -> str:
    return "train:last_train_time"


@lru_cache(maxsize=settings.vector_cache_size)
def cached_vector_computation(item_id: int, features_json: str) -> Tuple[int, str]:
    return (item_id, features_json)


def generate_reason(user_profile: Dict[str, Any], item_features: Dict[str, Any], strategy: str) -> str:
    if strategy == "hotness":
        return "当前热门推荐"
    elif strategy == "collaborative":
        return "与您兴趣相似的用户也喜欢"
    elif strategy == "content":
        categories = item_features.get("categories", [])
        if categories and user_profile.get("preferred_categories"):
            common = set(categories) & set(user_profile["preferred_categories"])
            if common:
                return f"因为您关注{', '.join(list(common)[:2])}相关内容"
        return "因为您喜欢过类似的内容"
    elif strategy == "hybrid":
        reasons = []
        if item_features.get("is_hot"):
            reasons.append("热门推荐")
        if user_profile.get("preferred_categories"):
            categories = item_features.get("categories", [])
            common = set(categories) & set(user_profile["preferred_categories"])
            if common:
                reasons.append(f"您关注的{list(common)[0]}")
        if reasons:
            return " + ".join(reasons[:2])
        return "为您个性化推荐"
    return "为您推荐"


def parse_timestamp(timestamp: Any) -> int:
    if isinstance(timestamp, (int, float)):
        return int(timestamp)
    if isinstance(timestamp, str):
        try:
            return int(timestamp)
        except ValueError:
            return int(time.time())
    return int(time.time())
