import time
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from surprise import SVD, Dataset, Reader
import pandas as pd
import numpy as np
from models.database import Database
from core.config import settings
from core.redis_client import RedisClient
from core.utils import (
    min_max_normalize,
    get_train_counter_key,
    get_last_train_time_key,
)


class CollaborativeRecommender:
    def __init__(self, db: Database, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.model: Optional[SVD] = None
        self.trainset = None
        self._is_trained = False
        self._training_lock = asyncio.Lock()
        self._last_train_time = 0
        self._item_id_to_inner = {}
        self._inner_to_item_id = {}
        self._user_id_to_inner = {}
        self._inner_to_user_id = {}

    async def train(self, incremental: bool = False) -> bool:
        async with self._training_lock:
            try:
                train_start = time.time()

                since_timestamp = 0
                if incremental and self._last_train_time > 0:
                    since_timestamp = self._last_train_time

                behaviors = await self.db.get_all_behaviors_for_training(
                    since_timestamp=since_timestamp
                )

                if not behaviors:
                    print("No training data available")
                    return False

                print(f"Training with {len(behaviors)} behavior records...")

                reader = Reader(rating_scale=(1, 6))

                df = pd.DataFrame(
                    behaviors,
                    columns=["userID", "itemID", "rating"],
                )
                df["userID"] = df["userID"].astype(str)
                df["itemID"] = df["itemID"].astype(str)

                data = Dataset.load_from_df(df[["userID", "itemID", "rating"]], reader)

                full_trainset = data.build_full_trainset()

                self._user_id_to_inner = {}
                self._inner_to_user_id = {}
                for inner_id in full_trainset.ur.keys():
                    raw_user_id = int(full_trainset.to_raw_uid(inner_id))
                    self._user_id_to_inner[raw_user_id] = inner_id
                    self._inner_to_user_id[inner_id] = raw_user_id

                self._item_id_to_inner = {}
                self._inner_to_item_id = {}
                for inner_id in full_trainset.ir.keys():
                    raw_item_id = int(full_trainset.to_raw_iid(inner_id))
                    self._item_id_to_inner[raw_item_id] = inner_id
                    self._inner_to_item_id[inner_id] = raw_item_id

                if not incremental or self.model is None:
                    self.model = SVD(
                        n_factors=settings.svd_n_factors,
                        random_state=settings.svd_random_state,
                        biased=True,
                    )

                self.model.fit(full_trainset)
                self.trainset = full_trainset
                self._is_trained = True
                self._last_train_time = int(time.time())

                try:
                    await self.redis.set(
                        get_last_train_time_key(),
                        str(self._last_train_time),
                    )
                    await self.redis.set(get_train_counter_key(), "0")
                except Exception as redis_err:
                    print(f"Warning: Failed to update Redis train metadata: {redis_err}")

                train_duration = time.time() - train_start
                print(
                    f"Model training completed in {train_duration:.2f}s, "
                    f"behaviors: {len(behaviors)}, users: {len(self._user_id_to_inner)}, "
                    f"items: {len(self._item_id_to_inner)}, incremental: {incremental}"
                )

                return True

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Model training failed: {e}")
                self._is_trained = False
                return False

    async def check_and_trigger_training(self) -> None:
        try:
            counter = await self.redis.get(get_train_counter_key())
            counter = int(counter) if counter else 0

            last_train = await self.redis.get(get_last_train_time_key())
            last_train = int(last_train) if last_train else 0

            current_time = int(time.time())
            time_since_train = current_time - last_train

            need_train = (
                counter >= settings.incremental_train_threshold
                or time_since_train >= settings.max_train_interval_seconds
            )

            if need_train and not self._training_lock.locked():
                asyncio.create_task(self.train(incremental=True))

        except Exception as e:
            print(f"Check training trigger failed: {e}")

    async def increment_behavior_counter(self) -> None:
        try:
            await self.redis.incr(get_train_counter_key())
        except Exception as e:
            print(f"Increment counter failed: {e}")

    async def recommend(
        self,
        user_id: int,
        count: int = 10,
        exclude_item_ids: List[int] = None,
    ) -> List[Tuple[int, float]]:
        if not self._is_trained or self.model is None:
            return []

        if exclude_item_ids is None:
            exclude_item_ids = []

        if user_id not in self._user_id_to_inner:
            return []

        candidate_items = [
            item_id for item_id in self._item_id_to_inner.keys()
            if item_id not in exclude_item_ids
        ]

        if not candidate_items:
            return []

        predictions = []
        for item_id in candidate_items:
            try:
                pred = self.model.predict(str(user_id), str(item_id))
                predictions.append((item_id, pred.est))
            except Exception:
                continue

        predictions.sort(key=lambda x: x[1], reverse=True)

        if not predictions:
            return []

        scores = [p[1] for p in predictions]
        normalized_scores = min_max_normalize(scores)

        result = []
        for i, (item_id, _) in enumerate(predictions[:count]):
            result.append((item_id, normalized_scores[i]))

        return result

    async def predict_rating(self, user_id: int, item_id: int) -> float:
        if not self._is_trained or self.model is None:
            return 0.0

        try:
            pred = self.model.predict(str(user_id), str(item_id))
            return float(pred.est)
        except Exception:
            return 0.0

    def is_trained(self) -> bool:
        return self._is_trained

    def get_model_stats(self) -> Dict[str, Any]:
        return {
            "is_trained": self._is_trained,
            "num_users": len(self._user_id_to_inner),
            "num_items": len(self._item_id_to_inner),
            "last_train_time": self._last_train_time,
            "n_factors": settings.svd_n_factors,
        }
