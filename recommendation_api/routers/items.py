from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
import json
from models.schemas import (
    ItemCreate,
    ItemUpdate,
    ItemResponse,
    ItemListResponse,
    ErrorResponse,
)
from services.recommender import RecommendationEngine
from core.redis_client import get_redis_client, RedisClient
from models.database import get_database, Database

router = APIRouter(prefix="/items", tags=["items"])


async def get_recommender(
    db: Database = Depends(get_database),
    redis: RedisClient = Depends(get_redis_client),
) -> RecommendationEngine:
    return RecommendationEngine(db, redis)


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

        await recommender.content_based.build_index()

        cache_keys = await recommender.redis._client.keys("rec:*")
        for key in cache_keys:
            await recommender.redis.delete(key)

        return ItemResponse(**created_item)

    except HTTPException:
        raise
    except Exception as e:
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
            import time
            update_fields.append("updated_at = ?")
            update_values.append(int(time.time()))
            update_values.append(item_id)

            async with recommender.db._conn_pool() if hasattr(recommender.db, '_conn_pool') else None:
                import aiosqlite
                from core.config import settings
                async with aiosqlite.connect(settings.items_db_path) as db:
                    await db.execute(
                        f"UPDATE items SET {', '.join(update_fields)} WHERE id = ?",
                        update_values,
                    )
                    await db.commit()

        await recommender.content_based.build_index()

        updated_item = await recommender.db.get_item(item_id)
        return ItemResponse(**updated_item)

    except HTTPException:
        raise
    except Exception as e:
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

        import aiosqlite
        from core.config import settings
        async with aiosqlite.connect(settings.items_db_path) as db:
            await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
            await db.commit()

        await recommender.content_based.build_index()

        return {"status": "ok", "message": f"物品 {item_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
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
