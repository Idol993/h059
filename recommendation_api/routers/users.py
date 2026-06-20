from fastapi import APIRouter, HTTPException, Depends, Request
from models.schemas import (
    BehaviorRequest,
    BehaviorResponse,
    ErrorResponse,
    UserProfile,
)
from services.recommender import RecommendationEngine
from services import get_engine

router = APIRouter(prefix="", tags=["users"])


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


@router.post(
    "/behavior",
    response_model=BehaviorResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def report_behavior(
    request: Request,
    behavior: BehaviorRequest,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        item = await recommender.db.get_item(behavior.item_id)
        if not item:
            raise HTTPException(
                status_code=400,
                detail=f"item_id {behavior.item_id} 不存在",
            )

        await recommender.record_behavior(
            user_id=behavior.user_id,
            item_id=behavior.item_id,
            action_type=behavior.action.value,
            timestamp=behavior.timestamp,
            ab_group=behavior.ab_group,
        )

        return BehaviorResponse(
            status="ok",
            message="行为已记录，推荐结果将在下次刷新时更新",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Report behavior error: {e}")
        raise HTTPException(
            status_code=500,
            detail="行为记录失败，请稍后重试",
        )


@router.get("/user/{user_id}/profile")
async def get_user_profile(
    user_id: int,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        profile = await recommender.get_user_profile(user_id)

        return UserProfile(
            user_id=user_id,
            preferred_categories=profile.get("preferred_categories", []),
            preferred_tags=profile.get("preferred_tags", []),
            interaction_count=profile.get("interaction_count", 0),
            last_active=profile.get("last_active", 0),
        )

    except Exception as e:
        print(f"Get user profile error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取用户画像失败",
        )


@router.get("/user/{user_id}/behaviors")
async def get_user_behaviors(
    user_id: int,
    limit: int = 100,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        behaviors = await recommender.db.get_user_behaviors(user_id, limit=limit)

        item_ids = [b["item_id"] for b in behaviors]
        items = await recommender.db.get_items(item_ids)
        item_map = {item["id"]: item for item in items}

        result = []
        for b in behaviors:
            item = item_map.get(b["item_id"], {})
            result.append({
                "id": b["id"],
                "item_id": b["item_id"],
                "item_title": item.get("title", ""),
                "action": b["action_type"],
                "timestamp": b["timestamp"],
                "ab_group": b.get("ab_group", "default"),
            })

        return {
            "user_id": user_id,
            "count": len(result),
            "behaviors": result,
        }

    except Exception as e:
        print(f"Get user behaviors error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取用户行为失败",
        )
