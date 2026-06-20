import time
from typing import List, Dict, Any, Tuple
from models.database import Database
from core.utils import time_decay_score, min_max_normalize


class HotnessRecommender:
    def __init__(self, db: Database):
        self.db = db

    async def recommend(
        self,
        count: int = 10,
        exclude_item_ids: List[int] = None,
    ) -> List[Tuple[int, float]]:
        if exclude_item_ids is None:
            exclude_item_ids = []

        items = await self.db.get_all_items(limit=1000)

        current_time = int(time.time())
        scored_items = []

        for item in items:
            if item["id"] in exclude_item_ids:
                continue

            score = time_decay_score(
                likes=item["likes"],
                comments=item["comments"],
                created_at=item["created_at"],
                current_time=current_time,
            )
            scored_items.append((item["id"], score, item))

        scored_items.sort(key=lambda x: x[1], reverse=True)

        if not scored_items:
            return []

        scores = [s[1] for s in scored_items]
        normalized_scores = min_max_normalize(scores)

        result = []
        for i, (item_id, _, _) in enumerate(scored_items[:count]):
            result.append((item_id, normalized_scores[i]))

        return result

    async def get_hot_items(
        self,
        count: int = 100,
        category: str = None,
    ) -> List[Dict[str, Any]]:
        items = await self.db.get_all_items(limit=1000)

        if category:
            items = [
                item for item in items
                if category in item.get("categories", [])
            ]

        current_time = int(time.time())
        for item in items:
            item["hotness_score"] = time_decay_score(
                likes=item["likes"],
                comments=item["comments"],
                created_at=item["created_at"],
                current_time=current_time,
            )

        items.sort(key=lambda x: x["hotness_score"], reverse=True)
        return items[:count]
