import asyncio
import json
import random
import time
from models.database import get_database
from core.redis_client import get_redis_client
from core.utils import get_ab_config_key


SAMPLE_ITEMS = [
    {
        "title": "2024年人工智能发展趋势报告",
        "description": "深入分析AI技术在各行业的应用前景和最新突破",
        "categories": ["科技", "人工智能"],
        "tags": ["AI", "机器学习", "深度学习", "趋势"],
        "features": {"source": "tech_review", "quality": "high"},
        "likes": 1250,
        "comments": 89,
        "views": 15600,
    },
    {
        "title": "Python 3.12 新特性完全指南",
        "description": "详细介绍Python 3.12版本带来的性能优化和语法改进",
        "categories": ["科技", "编程"],
        "tags": ["Python", "编程语言", "教程"],
        "features": {"source": "python_official", "level": "intermediate"},
        "likes": 890,
        "comments": 56,
        "views": 12300,
    },
    {
        "title": "健康饮食：地中海饮食的科学依据",
        "description": "营养学家解读地中海饮食为何被评为最佳饮食方式",
        "categories": ["健康", "饮食"],
        "tags": ["健康", "饮食", "营养", "地中海"],
        "features": {"source": "health_mag", "read_time": 8},
        "likes": 2100,
        "comments": 156,
        "views": 28900,
    },
    {
        "title": "2024年最值得去的10个小众旅行目的地",
        "description": "避开人潮，探索世界上最美的隐秘角落",
        "categories": ["旅游", "生活方式"],
        "tags": ["旅行", "目的地", "小众", "攻略"],
        "features": {"source": "travel_blog", "has_images": True},
        "likes": 3400,
        "comments": 234,
        "views": 45600,
    },
    {
        "title": "深度学习入门：从零搭建神经网络",
        "description": "用Python和NumPy从零实现一个简单的神经网络",
        "categories": ["科技", "人工智能"],
        "tags": ["深度学习", "神经网络", "Python", "教程"],
        "features": {"source": "tech_blog", "level": "beginner"},
        "likes": 1560,
        "comments": 98,
        "views": 18900,
    },
    {
        "title": "职场新人必看：如何快速适应工作环境",
        "description": "资深HR分享职场生存法则和快速成长秘诀",
        "categories": ["职场", "教育"],
        "tags": ["职场", "新人", "职业发展"],
        "features": {"source": "career_guide", "type": "advice"},
        "likes": 1890,
        "comments": 145,
        "views": 23400,
    },
    {
        "title": "投资入门：指数基金定投完全指南",
        "description": "普通人也能学会的稳健投资方法，实现财富稳步增长",
        "categories": ["财经", "投资"],
        "tags": ["投资", "理财", "基金", "定投"],
        "features": {"source": "finance_blog", "has_video": True},
        "likes": 2780,
        "comments": 189,
        "views": 36700,
    },
    {
        "title": "健身减脂：科学燃脂的10个真相",
        "description": "运动生理学专家告诉你那些关于减脂的常见误区",
        "categories": ["健康", "健身"],
        "tags": ["健身", "减脂", "运动", "科学"],
        "features": {"source": "fitness_mag", "has_workout": True},
        "likes": 4500,
        "comments": 312,
        "views": 67800,
    },
    {
        "title": "React 18 并发特性深度解析",
        "description": "深入理解React 18的并发渲染机制和新API",
        "categories": ["科技", "编程"],
        "tags": ["React", "前端", "JavaScript", "框架"],
        "features": {"source": "frontend_blog", "level": "advanced"},
        "likes": 1120,
        "comments": 67,
        "views": 14500,
    },
    {
        "title": "如何培养孩子的阅读习惯",
        "description": "儿童教育专家分享让孩子爱上阅读的实用方法",
        "categories": ["教育", "亲子"],
        "tags": ["教育", "阅读", "亲子", "儿童"],
        "features": {"source": "parenting_mag", "age_group": "3-12"},
        "likes": 2340,
        "comments": 178,
        "views": 31200,
    },
    {
        "title": "新能源汽车选购指南2024",
        "description": "从续航、充电、性价比等维度全面分析热门车型",
        "categories": ["汽车", "科技"],
        "tags": ["新能源", "电动车", "汽车", "选购"],
        "features": {"source": "auto_mag", "has_comparison": True},
        "likes": 3100,
        "comments": 245,
        "views": 42300,
    },
    {
        "title": "居家收纳：让小空间变大的魔法",
        "description": "专业收纳师分享实用的家居整理技巧",
        "categories": ["生活方式", "家居"],
        "tags": ["收纳", "家居", "整理", "小空间"],
        "features": {"source": "home_blog", "has_images": True},
        "likes": 1670,
        "comments": 112,
        "views": 22800,
    },
    {
        "title": "大语言模型技术原理与应用",
        "description": "从Transformer到GPT，全面了解LLM的技术演进",
        "categories": ["科技", "人工智能"],
        "tags": ["LLM", "GPT", "NLP", "大模型"],
        "features": {"source": "ai_research", "type": "technical"},
        "likes": 2450,
        "comments": 189,
        "views": 35600,
    },
    {
        "title": "咖啡品鉴：从入门到精通",
        "description": "了解咖啡豆产地、烘焙、冲煮的完整知识体系",
        "categories": ["生活方式", "美食"],
        "tags": ["咖啡", "品鉴", "冲煮", "咖啡豆"],
        "features": {"source": "coffee_mag", "has_recipe": True},
        "likes": 1340,
        "comments": 78,
        "views": 16700,
    },
    {
        "title": "简历优化：让HR第一眼就看中你",
        "description": "资深面试官告诉你如何写出一份满分简历",
        "categories": ["职场", "求职"],
        "tags": ["简历", "求职", "面试", "职场"],
        "features": {"source": "hr_blog", "has_template": True},
        "likes": 1980,
        "comments": 156,
        "views": 27800,
    },
    {
        "title": "环保生活：日常中的低碳实践",
        "description": "简单易行的环保生活方式，为地球减负从我做起",
        "categories": ["环保", "生活方式"],
        "tags": ["环保", "低碳", "可持续", "绿色生活"],
        "features": {"source": "eco_blog", "type": "lifestyle"},
        "likes": 980,
        "comments": 56,
        "views": 12300,
    },
    {
        "title": "Vue 3 组合式API最佳实践",
        "description": "深入掌握Vue 3 Composition API的正确使用姿势",
        "categories": ["科技", "编程"],
        "tags": ["Vue", "前端", "JavaScript", "框架"],
        "features": {"source": "vue_official", "level": "intermediate"},
        "likes": 1450,
        "comments": 89,
        "views": 19200,
    },
    {
        "title": "睡眠质量提升完全手册",
        "description": "睡眠科医生分享改善睡眠的科学方法",
        "categories": ["健康", "生活方式"],
        "tags": ["睡眠", "健康", "失眠", "作息"],
        "features": {"source": "medical_blog", "type": "guide"},
        "likes": 3670,
        "comments": 267,
        "views": 51200,
    },
    {
        "title": "摄影入门：手机也能拍出大片",
        "description": "构图、光线、后期，手机摄影必备技巧",
        "categories": ["艺术", "摄影"],
        "tags": ["摄影", "手机摄影", "构图", "后期"],
        "features": {"source": "photo_blog", "has_examples": True},
        "likes": 2890,
        "comments": 198,
        "views": 38900,
    },
    {
        "title": "数字货币投资风险与机遇",
        "description": "理性看待加密货币市场，了解投资风险",
        "categories": ["财经", "投资"],
        "tags": ["加密货币", "比特币", "区块链", "投资"],
        "features": {"source": "finance_news", "type": "analysis"},
        "likes": 2120,
        "comments": 234,
        "views": 29800,
    },
]

SAMPLE_USERS = list(range(1, 21))

ACTION_TYPES = ["view", "click", "like", "favorite", "comment", "share"]


async def init_sample_data():
    print("开始初始化测试数据...")

    db = await get_database()
    redis = await get_redis_client()

    print("清空现有数据...")
    import aiosqlite
    from core.config import settings
    async with aiosqlite.connect(settings.items_db_path) as conn:
        await conn.execute("DELETE FROM items")
        await conn.execute("DELETE FROM sqlite_sequence WHERE name='items'")
        await conn.commit()
    async with aiosqlite.connect(settings.behaviors_db_path) as conn:
        await conn.execute("DELETE FROM behaviors")
        await conn.execute("DELETE FROM sqlite_sequence WHERE name='behaviors'")
        await conn.commit()

    print("清空Redis缓存...")
    try:
        keys = await redis._client.keys("*")
        if keys:
            await redis._client.delete(*keys)
    except Exception as e:
        print(f"Redis清空警告: {e}")

    print("初始化A/B测试配置...")
    await redis.hset(
        get_ab_config_key("A"),
        mapping={
            "hotness": "0.2",
            "collaborative": "0.5",
            "content": "0.3",
        },
    )
    await redis.hset(
        get_ab_config_key("B"),
        mapping={
            "hotness": "0.4",
            "collaborative": "0.3",
            "content": "0.3",
        },
    )

    print("创建示例物品...")
    current_time = int(time.time())
    item_ids = []
    for i, item in enumerate(SAMPLE_ITEMS):
        created_at = current_time - (len(SAMPLE_ITEMS) - i) * 3600 * 2
        item_id = await db.add_item(
            title=item["title"],
            description=item["description"],
            categories=item["categories"],
            tags=item["tags"],
            features=item["features"],
            created_at=created_at,
        )
        item_ids.append(item_id)

        import aiosqlite
        async with aiosqlite.connect(settings.items_db_path) as conn:
            await conn.execute(
                "UPDATE items SET likes=?, comments=?, views=? WHERE id=?",
                (item["likes"], item["comments"], item["views"], item_id),
            )
            await conn.commit()

    print(f"已创建 {len(item_ids)} 个示例物品")

    print("创建示例行为数据...")
    random.seed(42)

    for user_id in SAMPLE_USERS:
        num_behaviors = random.randint(8, 20)
        user_interests = random.sample(range(len(item_ids)), random.randint(5, 10))

        for _ in range(num_behaviors):
            if random.random() < 0.7 and user_interests:
                item_idx = random.choice(user_interests)
            else:
                item_idx = random.randint(0, len(item_ids) - 1)

            item_id = item_ids[item_idx]
            action_type = random.choices(
                ACTION_TYPES,
                weights=[0.4, 0.25, 0.15, 0.1, 0.07, 0.03],
                k=1,
            )[0]

            timestamp = current_time - random.randint(0, 3600 * 48)
            ab_group = random.choice(["default", "A", "B"])

            await db.add_behavior(
                user_id=user_id,
                item_id=item_id,
                action_type=action_type,
                timestamp=timestamp,
                ab_group=ab_group,
            )

    print(f"已创建行为数据")

    print("\n数据统计:")
    print(f"- 物品数量: {len(item_ids)}")
    total_behaviors = 0
    for user_id in SAMPLE_USERS:
        count = await db.get_user_behavior_count(user_id)
        total_behaviors += count
    print(f"- 总行为数: {total_behaviors}")
    print(f"- 用户数量: {len(SAMPLE_USERS)}")

    print("\n示例用户行为统计:")
    for user_id in [1, 2, 3]:
        count = await db.get_user_behavior_count(user_id)
        behaviors = await db.get_user_behaviors(user_id, limit=5)
        print(f"  用户 {user_id}: {count} 条行为, 最近行为: {[b['action_type'] for b in behaviors]}")

    print("\n测试数据初始化完成!")
    print("可以使用以下命令启动服务:")
    print("  cd recommendation_api && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    print("\nAPI文档地址:")
    print("  Swagger UI: http://localhost:8000/docs")
    print("  ReDoc: http://localhost:8000/redoc")


if __name__ == "__main__":
    asyncio.run(init_sample_data())
