import asyncio
import httpx
import json


BASE_URL = "http://localhost:8000"


async def test_health_check():
    print("=" * 60)
    print("测试健康检查接口...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        assert response.status_code == 200
        print("✓ 健康检查测试通过")


async def test_root():
    print("\n" + "=" * 60)
    print("测试根路径接口...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/")
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"应用名称: {data['name']}")
        print(f"可用端点: {list(data['endpoints'].keys())}")
        assert response.status_code == 200
        print("✓ 根路径测试通过")


async def test_list_items():
    print("\n" + "=" * 60)
    print("测试获取物品列表接口...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/items", params={"limit": 5})
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"返回物品数: {len(data['items'])}/{data['total']}")
        for item in data["items"][:2]:
            print(f"  - {item['id']}: {item['title'][:30]}...")
        assert response.status_code == 200
        print("✓ 物品列表测试通过")
        return data["items"][0]["id"] if data["items"] else None


async def test_get_item(item_id: int):
    print("\n" + "=" * 60)
    print(f"测试获取物品详情接口 (ID: {item_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/items/{item_id}")
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"标题: {data['title']}")
        print(f"分类: {data['categories']}")
        print(f"标签: {data['tags']}")
        print(f"点赞/评论/浏览: {data['likes']}/{data['comments']}/{data['views']}")
        assert response.status_code == 200
        print("✓ 物品详情测试通过")


async def test_hot_recommendations():
    print("\n" + "=" * 60)
    print("测试热门推荐接口...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/recommend/hot", params={"count": 5})
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"返回热门物品数: {data['count']}")
        for item in data["items"]:
            print(f"  - {item['id']}: {item['title'][:30]}... (热度: {item['hotness_score']:.4f})")
        assert response.status_code == 200
        print("✓ 热门推荐测试通过")


async def test_similar_items(item_id: int):
    print("\n" + "=" * 60)
    print(f"测试相似物品接口 (ID: {item_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/recommend/similar/{item_id}", params={"count": 5})
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"相似物品数: {len(data['similar_items'])}")
        for item in data["similar_items"]:
            print(f"  - {item['id']}: {item['title'][:30]}... (相似度: {item['score']:.4f})")
        assert response.status_code == 200
        print("✓ 相似物品测试通过")


async def test_user_profile(user_id: int):
    print("\n" + "=" * 60)
    print(f"测试获取用户画像接口 (用户ID: {user_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/user/{user_id}/profile")
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"用户ID: {data['user_id']}")
        print(f"偏好分类: {data['preferred_categories'][:5]}")
        print(f"偏好标签: {data['preferred_tags'][:5]}")
        print(f"交互次数: {data['interaction_count']}")
        assert response.status_code == 200
        print("✓ 用户画像测试通过")


async def test_user_behaviors(user_id: int):
    print("\n" + "=" * 60)
    print(f"测试获取用户行为接口 (用户ID: {user_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/user/{user_id}/behaviors", params={"limit": 5})
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"返回行为数: {data['count']}")
        for b in data["behaviors"]:
            print(f"  - {b['action']}: {b['item_title'][:20]}... (AB组: {b['ab_group']})")
        assert response.status_code == 200
        print("✓ 用户行为测试通过")


async def test_hybrid_recommendation(user_id: int):
    print("\n" + "=" * 60)
    print(f"测试混合推荐接口 (用户ID: {user_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/recommend",
            params={
                "user_id": user_id,
                "count": 10,
                "strategy": "hybrid",
                "ab_group": "A",
            },
        )
        print(f"状态码: {response.status_code}")
        print(f"X-AB-Group Header: {response.headers.get('X-AB-Group')}")
        data = response.json()
        print(f"用户ID: {data['user_id']}")
        print(f"策略: {data['strategy']}")
        print(f"AB组: {data['ab_group']}")
        print(f"推荐物品数: {len(data['items'])}")
        for item in data["items"]:
            print(f"  - {item['id']}: 分数={item['score']:.4f}, 原因: {item['reason']}")
        assert response.status_code == 200
        print("✓ 混合推荐测试通过")


async def test_report_behavior(user_id: int, item_id: int):
    print("\n" + "=" * 60)
    print(f"测试行为上报接口 (用户ID: {user_id}, 物品ID: {item_id})...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/behavior",
            json={
                "user_id": user_id,
                "item_id": item_id,
                "action": "like",
                "timestamp": 1719216000,
                "ab_group": "A",
            },
        )
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"响应: {data}")
        assert response.status_code == 200
        print("✓ 行为上报测试通过")


async def test_create_item():
    print("\n" + "=" * 60)
    print("测试创建物品接口...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/items",
            json={
                "title": "测试文章：FastAPI快速上手教程",
                "description": "从零开始学习FastAPI框架的使用方法",
                "categories": ["科技", "编程"],
                "tags": ["FastAPI", "Python", "后端"],
                "features": {"level": "beginner", "read_time": 10},
            },
        )
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"创建成功，物品ID: {data['id']}")
        print(f"标题: {data['title']}")
        assert response.status_code == 200
        print("✓ 创建物品测试通过")
        return data["id"]


async def test_rebuild_index():
    print("\n" + "=" * 60)
    print("测试重建内容索引接口...")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/items/rebuild-index")
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"索引状态: {data['index_built']}")
        assert response.status_code == 200
        print("✓ 重建索引测试通过")


async def test_train_model():
    print("\n" + "=" * 60)
    print("测试训练协同过滤模型接口...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/items/train-model",
            params={"incremental": False},
        )
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"训练状态: {data['status']}")
        print(f"模型统计: {data['stats']}")
        assert response.status_code == 200
        print("✓ 模型训练测试通过")


async def main():
    print("推荐系统 API 测试套件")
    print("=" * 60)
    print(f"目标地址: {BASE_URL}")

    try:
        await test_health_check()
        await test_root()

        first_item_id = await test_list_items()
        if first_item_id:
            await test_get_item(first_item_id)
            await test_similar_items(first_item_id)

        await test_hot_recommendations()

        test_user_id = 1
        await test_user_profile(test_user_id)
        await test_user_behaviors(test_user_id)
        await test_hybrid_recommendation(test_user_id)

        if first_item_id:
            await test_report_behavior(test_user_id, first_item_id)

        await test_create_item()
        await test_rebuild_index()
        await test_train_model()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
