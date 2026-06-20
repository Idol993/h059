import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.config import settings
from core.redis_client import get_redis_client
from models.database import get_database
from services.recommender import RecommendationEngine
from models.schemas import HealthResponse, ErrorResponse
from routers import recommendations, users, items

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        logger.info(f"Request started: {method} {path} from {client_ip}")

        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
            logger.info(
                f"Request completed: {method} {path} "
                f"status={response.status_code} duration={process_time:.2f}ms"
            )
            return response
        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {method} {path} "
                f"error={str(e)} duration={process_time:.2f}ms",
                exc_info=True,
            )
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting recommendation API service...")

    try:
        redis = await get_redis_client()
        redis_connected = await redis.is_connected()
        logger.info(f"Redis connected: {redis_connected}")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")

    try:
        db = await get_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    try:
        from services import set_engine
        recommender = RecommendationEngine(db, redis)
        app.state.recommender = recommender
        set_engine(recommender)
        logger.info("Recommendation engine created and registered globally")

        await recommender.content_based.build_index()
        logger.info(
            f"Content index built: {recommender.content_based.is_built()}, "
            f"items: {len(recommender.content_based.item_ids)}"
        )

        train_success = await recommender.collaborative.train(incremental=False)
        logger.info(
            f"Collaborative model trained: {train_success}, "
            f"stats: {recommender.collaborative.get_model_stats()}"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.warning(f"Model initialization warning: {e}")

    logger.info("Recommendation API service started successfully")

    yield

    logger.info("Shutting down recommendation API service...")
    try:
        from core.redis_client import redis_client
        await redis_client.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    logger.info("Recommendation API service stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        description="实时推荐系统 API 服务，支持热门推荐、协同过滤、内容相似度等多种推荐策略",
        lifespan=lifespan,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestLoggingMiddleware)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "推荐服务内部错误，请稍后重试"},
        )

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={500: {"model": ErrorResponse}},
        tags=["system"],
    )
    async def health_check():
        try:
            from core.redis_client import redis_client
            redis_connected = await redis_client.is_connected()
        except Exception:
            redis_connected = False

        model_ready = False
        if hasattr(app.state, "recommender"):
            health_status = app.state.recommender.get_health_status()
            model_ready = health_status.get("model_ready", False)

        return HealthResponse(
            status="healthy",
            model_ready=model_ready,
            redis_connected=redis_connected,
        )

    @app.get("/health/detailed", tags=["system"])
    async def detailed_health_check():
        try:
            from core.redis_client import redis_client
            redis_connected = await redis_client.is_connected()
        except Exception:
            redis_connected = False

        result = {
            "status": "healthy",
            "redis_connected": redis_connected,
            "model_ready": False,
            "details": {},
        }

        if hasattr(app.state, "recommender"):
            health_status = app.state.recommender.get_health_status()
            result.update(health_status)

        return result

    app.include_router(recommendations.router)
    app.include_router(users.router)
    app.include_router(items.router)

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.api_version,
            "endpoints": {
                "recommendations": "/recommend",
                "behavior_reporting": "/behavior",
                "item_management": "/items",
                "health_check": "/health",
            },
            "docs": {
                "swagger": "/docs",
                "redoc": "/redoc",
            },
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level,
    )
