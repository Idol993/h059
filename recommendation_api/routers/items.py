from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
import json
import time
import aiosqlite
from models.schemas import (
    ItemCreate,
    ItemUpdate,
    ItemResponse,
    ItemListResponse,
    ErrorResponse,
)
from services.recommender import RecommendationEngine
from services import get_engine
from core.config import settings

router = APIRouter(prefix="/items", tags=["items"])


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


async def clear_recommendation_cache(redis_client) -> None:
    try:
        if redis_client and redis_client._client:
            keys = await redis_client._client.keys("rec:*")
            if keys:
                await redis_client._client.delete(*keys)
    except Exception as e:
        print(f"Warning: Failed to clear recommendation cache: {e}")


@router.post(
    "",
    response_model=ItemResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_item(
    item: ItemCreate,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        item_id = await recommender.db.add_item(
            title=item.title,
            description=item.description or "",
            categories=item.categories or [],
            tags=item.tags or [],
            features=item.features or {},
            created_at=item.created_at,
        )

        created_item = await recommender.db.get_item(item_id)
        if not created_item:
            raise HTTPException(status_code=500, detail="创建物品失败")

        try:
            await recommender.content_based.build_index()
        except Exception as idx_err:
            print(f"Warning: Build index failed after create item: {idx_err}")

        await clear_recommendation_cache(recommender.redis)

        return ItemResponse(**created_item)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Create item error: {e}")
        raise HTTPException(
            status_code=500,
            detail="创建物品失败",
        )


@router.get(
    "",
    response_model=ItemListResponse,
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_items(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        items = await recommender.db.get_all_items(limit=10000)

        if category:
            items = [
                item for item in items
                if category in item.get("categories", [])
            ]

        total = len(items)
        items = items[offset : offset + limit]

        return ItemListResponse(
            items=[ItemResponse(**item) for item in items],
            total=total,
        )

    except Exception as e:
        print(f"List items error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取物品列表失败",
        )


@router.get(
    "/{item_id}",
    response_model=ItemResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_item(
    item_id: int,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        item = await recommender.db.get_item(item_id)
        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"物品 {item_id} 不存在",
            )

        return ItemResponse(**item)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get item error: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取物品详情失败",
        )


@router.put(
    "/{item_id}",
    response_model=ItemResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        existing_item = await recommender.db.get_item(item_id)
        if not existing_item:
            raise HTTPException(
                status_code=404,
                detail=f"物品 {item_id} 不存在",
            )

        update_fields = []
        update_values = []

        if item_update.title is not None:
            update_fields.append("title = ?")
            update_values.append(item_update.title)

        if item_update.description is not None:
            update_fields.append("description = ?")
            update_values.append(item_update.description)

        if item_update.categories is not None:
            update_fields.append("categories = ?")
            update_values.append(json.dumps(item_update.categories, ensure_ascii=False))

        if item_update.tags is not None:
            update_fields.append("tags = ?")
            update_values.append(json.dumps(item_update.tags, ensure_ascii=False))

        if item_update.features is not None:
            update_fields.append("features_json = ?")
            update_values.append(json.dumps(item_update.features, ensure_ascii=False))

        if update_fields:
            update_fields.append("updated_at = ?")
            update_values.append(int(time.time()))
            update_values.append(item_id)

            async with aiosqlite.connect(settings.items_db_path) as db:
                await db.execute(
                    f"UPDATE items SET {', '.join(update_fields)} WHERE id = ?",
                    tuple(update_values),
                )
                await db.commit()

        try:
            await recommender.content_based.build_index()
        except Exception as idx_err:
            print(f"Warning: Build index failed after update item: {idx_err}")

        await clear_recommendation_cache(recommender.redis)

        updated_item = await recommender.db.get_item(item_id)
        return ItemResponse(**updated_item)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Update item error: {e}")
        raise HTTPException(
            status_code=500,
            detail="更新物品失败",
        )


@router.delete(
    "/{item_id}",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_item(
    item_id: int,
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        existing_item = await recommender.db.get_item(item_id)
        if not existing_item:
            raise HTTPException(
                status_code=404,
                detail=f"物品 {item_id} 不存在",
            )

        async with aiosqlite.connect(settings.items_db_path) as db:
            await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
            await db.commit()

        try:
            await recommender.content_based.build_index()
        except Exception as idx_err:
            print(f"Warning: Build index failed after delete item: {idx_err}")

        await clear_recommendation_cache(recommender.redis)

        return {"status": "ok", "message": f"物品 {item_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Delete item error: {e}")
        raise HTTPException(
            status_code=500,
            detail="删除物品失败",
        )


@router.post("/rebuild-index")
async def rebuild_content_index(
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        await recommender.content_based.build_index()
        return {
            "status": "ok",
            "message": "内容索引已重建",
            "index_built": recommender.content_based.is_built(),
        }
    except Exception as e:
        print(f"Rebuild index error: {e}")
        raise HTTPException(
            status_code=500,
            detail="重建索引失败",
        )


@router.post("/train-model")
async def train_collaborative_model(
    incremental: bool = Query(False, description="是否增量训练"),
    recommender: RecommendationEngine = Depends(get_recommender),
):
    try:
        success = await recommender.collaborative.train(incremental=incremental)
        stats = recommender.collaborative.get_model_stats()

        return {
            "status": "ok" if success else "failed",
            "message": "模型训练完成" if success else "模型训练失败（可能没有足够的行为数据）",
            "incremental": incremental,
            "stats": stats,
        }
    except Exception as e:
        print(f"Train model error: {e}")
        raise HTTPException(
            status_code=500,
            detail="模型训练失败",
        )
