import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_core():
    print("=" * 60)
    print("本地核心链路测试")
    print("=" * 60)

    from models.database import get_database
    from core.redis_client import get_redis_client
    from services import RecommendationEngine

    print("\n[1/5] 初始化数据库...")
    db = await get_database()
    print("  ✓ 数据库初始化成功")

    print("\n[2/5] 初始化 Redis...")
    redis = await get_redis_client()
    redis_ok = await redis.is_connected()
    print(f"  {'✓' if redis_ok else '⚠'} Redis 连接状态: {redis_ok}")

    print("\n[3/5] 创建推荐引擎...")
    engine = RecommendationEngine(db, redis)
    print("  ✓ 推荐引擎创建成功")

    print("\n[4/5] 构建内容索引...")
    await engine.content_based.build_index()
    print(f"  ✓ 内容索引构建完成, 物品数: {len(engine.content_based.item_ids)}")
    print(f"  ✓ 索引状态: {engine.content_based.is_built()}")

    print("\n[5/5] 训练协同过滤模型...")
    success = await engine.collaborative.train(incremental=False)
    print(f"  训练状态: {'✓ 成功' if success else '✗ 失败'}")
    stats = engine.collaborative.get_model_stats()
    print(f"  统计信息: {stats}")

    print("\n" + "=" * 60)
    print("健康检查:")
    health = engine.get_health_status()
    print(f"  model_ready: {health['model_ready']}")
    print(f"  collaborative_trained: {health['collaborative_trained']}")
    print(f"  content_index_built: {health['content_index_built']}")
    print("=" * 60)

    if success:
        print("\n✓ 协同过滤训练成功！现在测试推荐：")

        for user_id in [1, 2, 3]:
            behavior_count = await db.get_user_behavior_count(user_id)
            print(f"\n  用户 {user_id} 行为数: {behavior_count}")

            items, ab_group = await engine.recommend(
                user_id=user_id,
                count=5,
                strategy="collaborative",
                ab_group="default",
            )

            if items:
                print(f"  协同过滤推荐结果:")
                for item in items:
                    print(f"    - 物品 {item.id}: 分数={item.score}, 原因={item.reason}")
            else:
                print(f"  协同过滤无结果（可能行为不足）")

            items2, _ = await engine.recommend(
                user_id=user_id,
                count=5,
                strategy="hybrid",
                ab_group="A",
            )
            if items2:
                print(f"  混合推荐结果:")
                for item in items2[:3]:
                    print(f"    - 物品 {item.id}: 分数={item.score}, 原因={item.reason}")

        print("\n" + "=" * 60)
        print("测试 PUT 更新物品...")
        import json
        import time
        import aiosqlite
        from core.config import settings

        test_item_id = 1
        item = await db.get_item(test_item_id)
        if item:
            print(f"  更新前: 标题='{item['title'][:30]}...', 分类={item['categories']}")

            new_title = "【更新测试】" + item["title"]
            new_categories = ["测试分类"] + (item["categories"] or [])

            async with aiosqlite.connect(settings.items_db_path) as conn:
                await conn.execute(
                    "UPDATE items SET title=?, categories=?, updated_at=? WHERE id=?",
                    (new_title, json.dumps(new_categories, ensure_ascii=False), int(time.time()), test_item_id),
                )
                await conn.commit()

            await engine.content_based.build_index()

            updated = await db.get_item(test_item_id)
            print(f"  更新后: 标题='{updated['title'][:30]}...', 分类={updated['categories']}")
            print(f"  ✓ PUT 更新测试通过")
        else:
            print(f"  物品 {test_item_id} 不存在，跳过更新测试")

    print("\n" + "=" * 60)
    print("所有核心测试完成!")
    print("=" * 60)

    await redis.close()


if __name__ == "__main__":
    asyncio.run(test_core())
