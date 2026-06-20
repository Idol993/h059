import json
import time
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from models.database import Database
from models.schemas import RecommendedItem
from core.redis_client import RedisClient
from core.config import settings, get_strategy_weights
from core.utils import (
    get_recommend_cache_key,
    get_user_profile_key,
    get_ab_config_key,
    generate_reason,
)
from .hotness import HotnessRecommender
from .content_based import ContentBasedRecommender
from .collaborative import CollaborativeRecommender


class RecommendationEngine:
    def __init__(self, db: Database, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.hotness = HotnessRecommender(db)
        self.content_based = ContentBasedRecommender(db)
        self.collaborative = CollaborativeRecommender(db, redis)

    async def initialize(self) -> None:
        await self.content_based.build_index()
        await self.collaborative.train(incremental=False)

    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        cache_key = get_user_profile_key(user_id)
        cached = await self.redis.get_json(cache_key)
        if cached:
            return cached

        behaviors = await self.db.get_user_behaviors(user_id, limit=1000)

        preferred_categories = defaultdict(int)
        preferred_tags = defaultdict(int)
        liked_items = []
        viewed_items = []
        last_active = 0

        item_ids = [b["item_id"] for b in behaviors]
        items = await self.db.get_items(item_ids)
        item_map = {item["id"]: item for item in items}

        for behavior in behaviors:
            action_type = behavior["action_type"]
            timestamp = behavior["timestamp"]
            item_id = behavior["item_id"]
            item = item_map.get(item_id)

            if timestamp > last_active:
                last_active = timestamp

            if action_type in ["like", "favorite"]:
                liked_items.append(item_id)
            elif action_type in ["view", "click"]:
                viewed_items.append(item_id)

            if item:
                weight = 1.0
                if action_type == "like":
                    weight = 3.0
                elif action_type == "favorite":
                    weight = 4.0
                elif action_type == "comment":
                    weight = 2.0

                for category in item.get("categories", []):
                    preferred_categories[category] += weight
                for tag in item.get("tags", []):
                    preferred_tags[tag] += weight

        sorted_categories = sorted(
            preferred_categories.items(), key=lambda x: x[1], reverse=True
        )
        sorted_tags = sorted(
            preferred_tags.items(), key=lambda x: x[1], reverse=True
        )

        profile = {
            "user_id": user_id,
            "preferred_categories": [c[0] for c in sorted_categories[:10]],
            "preferred_tags": [t[0] for t in sorted_tags[:20]],
            "liked_items": list(set(liked_items)),
            "viewed_items": list(set(viewed_items)),
            "interaction_count": len(behaviors),
            "last_active": last_active,
        }

        await self.redis.set_json(cache_key, profile, settings.user_profile_cache_ttl)
        return profile

    async def invalidate_user_profile(self, user_id: int) -> None:
        cache_key = get_user_profile_key(user_id)
        await self.redis.delete(cache_key)

    async def get_ab_weights(self, ab_group: str) -> Dict[str, float]:
        config_key = get_ab_config_key(ab_group)
        ab_config = await self.redis.hgetall(config_key)

        if ab_config:
            try:
                return {
                    "hotness": float(ab_config.get("hotness", settings.hotness_weight)),
                    "collaborative": float(ab_config.get("collaborative", settings.collaborative_weight)),
                    "content": float(ab_config.get("content", settings.content_weight)),
                }
            except (ValueError, TypeError):
                pass

        return get_strategy_weights(ab_group)

    async def recommend(
        self,
        user_id: int,
        count: int = 10,
        strategy: str = "hybrid",
        ab_group: str = "default",
    ) -> Tuple[List[RecommendedItem], str]:
        cache_key = get_recommend_cache_key(user_id, strategy, ab_group)
        cached = await self.redis.get_json(cache_key)
        if cached:
            items = [RecommendedItem(**item) for item in cached]
            return items, ab_group

        behavior_count = await self.db.get_user_behavior_count(user_id)

        if strategy == "collaborative" and behavior_count < settings.min_user_behaviors:
            return [], ab_group

        user_profile = await self.get_user_profile(user_id)
        exclude_item_ids = list(set(
            user_profile.get("liked_items", []) + user_profile.get("viewed_items", [])
        ))

        weights = await self.get_ab_weights(ab_group)

        try:
            recommendations = await self._get_recommendations_by_strategy(
                user_id=user_id,
                user_profile=user_profile,
                count=count * 3,
                strategy=strategy,
                exclude_item_ids=exclude_item_ids,
                weights=weights,
            )
        except Exception as e:
            print(f"Recommendation failed, falling back to hotness: {e}")
            recommendations = await self._fallback_recommend(
                count=count,
                exclude_item_ids=exclude_item_ids,
            )

        if not recommendations:
            recommendations = await self._fallback_recommend(
                count=count,
                exclude_item_ids=exclude_item_ids,
            )

        unique_items = self._dedupe_and_rank(recommendations, weights)

        item_ids = [item_id for item_id, _ in unique_items[:count]]
        items = await self.db.get_items(item_ids)
        item_map = {item["id"]: item for item in items}

        result = []
        for item_id, score in unique_items[:count]:
            item_features = item_map.get(item_id, {})
            reason = generate_reason(user_profile, item_features, strategy)
            result.append(
                RecommendedItem(
                    id=item_id,
                    score=round(float(score), 4),
                    reason=reason,
                )
            )

        if result:
            cache_data = [item.model_dump() for item in result]
            await self.redis.set_json(cache_key, cache_data, settings.recommendation_cache_ttl)

        return result, ab_group

    async def _get_recommendations_by_strategy(
        self,
        user_id: int,
        user_profile: Dict[str, Any],
        count: int,
        strategy: str,
        exclude_item_ids: List[int],
        weights: Dict[str, float],
    ) -> Dict[str, List[Tuple[int, float]]]:
        results = {}

        if strategy in ["hybrid", "hotness"]:
            hot_recs = await self.hotness.recommend(
                count=count,
                exclude_item_ids=exclude_item_ids,
            )
            results["hotness"] = hot_recs

        if strategy in ["hybrid", "collaborative"]:
            collab_recs = await self.collaborative.recommend(
                user_id=user_id,
                count=count,
                exclude_item_ids=exclude_item_ids,
            )
            results["collaborative"] = collab_recs

        if strategy in ["hybrid", "content"]:
            content_recs = await self.content_based.recommend(
                user_id=user_id,
                user_profile=user_profile,
                count=count,
                exclude_item_ids=exclude_item_ids,
            )
            results["content"] = content_recs

        return results

    def _dedupe_and_rank(
        self,
        recommendations: Dict[str, List[Tuple[int, float]]],
        weights: Dict[str, float],
    ) -> List[Tuple[int, float]]:
        item_scores: Dict[int, float] = defaultdict(float)

        for strategy, recs in recommendations.items():
            weight = weights.get(strategy, 0.0)
            if weight <= 0:
                continue
            for item_id, score in recs:
                item_scores[item_id] += score * weight

        ranked = sorted(item_scores.items(), key=lambda x: x[1], reverse=True)

        if ranked:
            scores = [s[1] for s in ranked]
            max_score = max(scores)
            if max_score > 0:
                ranked = [(item_id, score / max_score) for item_id, score in ranked]

        return ranked

    async def _fallback_recommend(
        self,
        count: int,
        exclude_item_ids: List[int],
    ) -> Dict[str, List[Tuple[int, float]]]:
        hot_recs = await self.hotness.recommend(
            count=count,
            exclude_item_ids=exclude_item_ids,
        )
        return {"hotness": hot_recs}

    async def record_behavior(
        self,
        user_id: int,
        item_id: int,
        action_type: str,
        timestamp: int,
        ab_group: str = "default",
    ) -> None:
        await self.db.add_behavior(
            user_id=user_id,
            item_id=item_id,
            action_type=action_type,
            timestamp=timestamp,
            ab_group=ab_group,
        )

        await self.db.update_item_stats(item_id=item_id, action_type=action_type)

        await self.invalidate_user_profile(user_id)

        cache_pattern = f"rec:{user_id}:*"
        try:
            keys = await self.redis._client.keys(cache_pattern)
            for key in keys:
                await self.redis.delete(key)
        except Exception as e:
            print(f"Clear recommendation cache failed: {e}")

        await self.collaborative.increment_behavior_counter()
        await self.collaborative.check_and_trigger_training()

    def get_health_status(self) -> Dict[str, Any]:
        return {
            "model_ready": self.collaborative.is_trained() and self.content_based.is_built(),
            "collaborative_trained": self.collaborative.is_trained(),
            "content_index_built": self.content_based.is_built(),
            "model_stats": self.collaborative.get_model_stats(),
        }
