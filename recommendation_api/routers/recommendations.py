from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional
from models.schemas import (
    RecommendationResponse,
    ErrorResponse,
    StrategyEnum,
)
from services.recommender import RecommendationEngine
from services import get_engine
from core.config import settings

router = APIRouter(prefix="/recommend", tags=["recommendations"])


async def get_recommender() -> RecommendationEngine:
    engine = get_engine()
    if engine is None:
        from services import set_engine
        from core.redis_client import get_redis_client, RedisClient
        from models.database import get_database, Database
        redis: RedisClient = await get_redis_client()
        db: Database = await get_database()
        engine = RecommendationEngine(db, redis)
        set_engine(engine)
    return engine


@router.get(
    "",
    response_model=RecommendationResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_recommendations(
    request: Request,
    user_id: int = Query(..., description="用户ID"),
    count: int = Query(10, ge=1, le=100, description="返回推荐数量"),
    strategy: StrategyEnum = Query(StrategyEnum.HYBRID, description="推荐策略"),
    ab_group: str = Query("default", description="A/B测试分组"),
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        behavior_count = await recommender.db.get_user_behavior_count(user_id)

        if strategy == StrategyEnum.COLLABORATIVE and behavior_count < settings.min_user_behaviors:
            raise HTTPException(
                status_code=400,
                detail=f"user_id 不存在或行为数据不足（至少需要 {settings.min_user_behaviors} 条）",
            )

        items, actual_ab_group = await recommender.recommend(
            user_id=user_id,
            count=count,
            strategy=strategy.value,
            ab_group=ab_group,
        )

        if not items:
            items, actual_ab_group = await recommender.recommend(
                user_id=user_id,
                count=count,
                strategy="hotness",
                ab_group=ab_group,
            )

        response = RecommendationResponse(
            user_id=user_id,
            strategy=strategy.value,
            items=items,
            ab_group=actual_ab_group,
        )

        headers = {"X-AB-Group": actual_ab_group}
        return JSONResponse(content=response.model_dump(), headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Recommendation error: {e}")
        raise HTTPException(
            status_code=500,
            detail="推荐服务内部错误，请稍后重试",
        )


@router.get("/similar/{item_id}")
async def get_similar_items(
    item_id: int,
    count: int = Query(10, ge=1, le=50),
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        similar_items = await recommender.content_based.find_similar_items(
            item_id=item_id,
            count=count,
        )

        item_ids = [item_id for item_id, _ in similar_items]
        items = await recommender.db.get_items(item_ids)
        item_map = {item["id"]: item for item in items}

        result = []
        for sim_item_id, score in similar_items:
            item = item_map.get(sim_item_id, {})
            result.append({
                "id": sim_item_id,
                "title": item.get("title", ""),
                "score": round(float(score), 4),
            })

        return {
            "item_id": item_id,
            "similar_items": result,
        }

    except Exception as e:
        print(f"Similar items error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取相似物品失败",
        )


@router.get("/hot")
async def get_hot_items(
    count: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="分类筛选"),
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        hot_items = await recommender.hotness.get_hot_items(
            count=count,
            category=category,
        )

        result = []
        for item in hot_items:
            result.append({
                "id": item["id"],
                "title": item["title"],
                "hotness_score": round(float(item.get("hotness_score", 0)), 4),
                "likes": item["likes"],
                "comments": item["comments"],
                "categories": item["categories"],
            })

        return {
            "count": len(result),
            "category": category,
            "items": result,
        }

    except Exception as e:
        print(f"Hot items error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取热门物品失败",
        )
