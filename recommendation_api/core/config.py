from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Recommendation API"
    api_version: str = "v1"
    debug: bool = False

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    items_db_path: str = "data/items.db"
    behaviors_db_path: str = "data/behaviors.db"

    recommendation_cache_ttl: int = 300
    user_profile_cache_ttl: int = 600

    hotness_weight: float = 0.3
    collaborative_weight: float = 0.4
    content_weight: float = 0.3

    svd_n_factors: int = 50
    svd_random_state: int = 42

    min_user_behaviors: int = 5
    incremental_train_threshold: int = 1000
    max_train_interval_seconds: int = 3600

    tfidf_max_features: int = 5000
    knn_neighbors: int = 50

    vector_cache_size: int = 10000

    default_ab_group: str = "default"

    log_level: str = "info"


settings = Settings()


def get_strategy_weights(ab_group: str = "default") -> Dict[str, float]:
    return {
        "hotness": settings.hotness_weight,
        "collaborative": settings.collaborative_weight,
        "content": settings.content_weight,
    }
