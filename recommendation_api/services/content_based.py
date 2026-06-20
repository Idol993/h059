import json
from typing import List, Dict, Any, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
import numpy as np
from models.database import Database
from core.config import settings
from core.utils import cached_vector_computation, min_max_normalize


class ContentBasedRecommender:
    def __init__(self, db: Database):
        self.db = db
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.nn_model: Optional[NearestNeighbors] = None
        self.item_ids: List[int] = []
        self.item_features: Dict[int, Dict[str, Any]] = {}
        self.tfidf_matrix: Optional[np.ndarray] = None
        self._is_built = False

    async def build_index(self) -> None:
        items = await self.db.get_all_items(limit=10000)

        if not items:
            self._is_built = False
            return

        self.item_ids = []
        self.item_features = {}
        texts = []

        for item in items:
            self.item_ids.append(item["id"])
            self.item_features[item["id"]] = item

            title = item.get("title", "")
            description = item.get("description", "")
            categories = " ".join(item.get("categories", []))
            tags = " ".join(item.get("tags", []))
            features_str = json.dumps(item.get("features", {}), ensure_ascii=False)

            combined_text = f"{title} {description} {categories} {tags} {features_str}"
            texts.append(combined_text)

            cached_vector_computation(item["id"], json.dumps(item, ensure_ascii=False))

        self.vectorizer = TfidfVectorizer(
            max_features=settings.tfidf_max_features,
            stop_words=None,
            ngram_range=(1, 2),
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

        self.nn_model = NearestNeighbors(
            n_neighbors=min(settings.knn_neighbors, len(self.item_ids)),
            metric="cosine",
            algorithm="brute",
            n_jobs=-1,
        )
        self.nn_model.fit(self.tfidf_matrix)

        self._is_built = True

    async def recommend(
        self,
        user_id: int,
        user_profile: Dict[str, Any],
        count: int = 10,
        exclude_item_ids: List[int] = None,
    ) -> List[Tuple[int, float]]:
        if not self._is_built:
            await self.build_index()

        if not self._is_built or not self.nn_model:
            return []

        if exclude_item_ids is None:
            exclude_item_ids = []

        preferred_categories = user_profile.get("preferred_categories", [])
        preferred_tags = user_profile.get("preferred_tags", [])

        liked_items = user_profile.get("liked_items", [])
        viewed_items = user_profile.get("viewed_items", [])

        query_text = ""
        if preferred_categories:
            query_text += " ".join(preferred_categories) + " "
        if preferred_tags:
            query_text += " ".join(preferred_tags) + " "

        for item_id in liked_items + viewed_items:
            if item_id in self.item_features:
                item = self.item_features[item_id]
                query_text += item.get("title", "") + " "
                query_text += " ".join(item.get("categories", [])) + " "
                query_text += " ".join(item.get("tags", [])) + " "

        if not query_text.strip():
            return []

        query_vector = self.vectorizer.transform([query_text])

        n_neighbors = min(settings.knn_neighbors, len(self.item_ids))
        distances, indices = self.nn_model.kneighbors(
            query_vector, n_neighbors=n_neighbors
        )

        scored_items = []
        for i, idx in enumerate(indices[0]):
            item_id = self.item_ids[idx]
            if item_id in exclude_item_ids:
                continue

            similarity = 1 - distances[0][i]
            item = self.item_features.get(item_id, {})

            category_boost = 1.0
            if preferred_categories:
                item_categories = item.get("categories", [])
                common = set(preferred_categories) & set(item_categories)
                if common:
                    category_boost += 0.2 * len(common)

            tag_boost = 1.0
            if preferred_tags:
                item_tags = item.get("tags", [])
                common = set(preferred_tags) & set(item_tags)
                if common:
                    tag_boost += 0.1 * len(common)

            final_score = similarity * category_boost * tag_boost
            scored_items.append((item_id, final_score))

        scored_items.sort(key=lambda x: x[1], reverse=True)

        if not scored_items:
            return []

        scores = [s[1] for s in scored_items]
        normalized_scores = min_max_normalize(scores)

        result = []
        for i, (item_id, _) in enumerate(scored_items[:count]):
            result.append((item_id, normalized_scores[i]))

        return result

    async def find_similar_items(
        self,
        item_id: int,
        count: int = 10,
    ) -> List[Tuple[int, float]]:
        if not self._is_built:
            await self.build_index()

        if not self._is_built or not self.nn_model:
            return []

        if item_id not in self.item_ids:
            return []

        item_idx = self.item_ids.index(item_id)
        item_vector = self.tfidf_matrix[item_idx]

        n_neighbors = min(count + 1, len(self.item_ids))
        distances, indices = self.nn_model.kneighbors(
            item_vector, n_neighbors=n_neighbors
        )

        result = []
        for i, idx in enumerate(indices[0]):
            similar_item_id = self.item_ids[idx]
            if similar_item_id == item_id:
                continue

            similarity = 1 - distances[0][i]
            result.append((similar_item_id, similarity))
            if len(result) >= count:
                break

        if result:
            scores = [s[1] for s in result]
            normalized_scores = min_max_normalize(scores)
            result = [(result[i][0], normalized_scores[i]) for i in range(len(result))]

        return result

    def is_built(self) -> bool:
        return self._is_built
