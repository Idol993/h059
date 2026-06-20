from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from enum import Enum


class StrategyEnum(str, Enum):
    HYBRID = "hybrid"
    HOTNESS = "hotness"
    COLLABORATIVE = "collaborative"
    CONTENT = "content"


class ActionEnum(str, Enum):
    VIEW = "view"
    CLICK = "click"
    LIKE = "like"
    FAVORITE = "favorite"
    COMMENT = "comment"
    SHARE = "share"


class RecommendedItem(BaseModel):
    id: int
    score: float
    reason: str


class RecommendationRequest(BaseModel):
    user_id: int
    count: int = Field(default=10, ge=1, le=100)
    strategy: StrategyEnum = StrategyEnum.HYBRID
    ab_group: str = "default"


class RecommendationResponse(BaseModel):
    user_id: int
    strategy: str
    items: List[RecommendedItem]
    ab_group: str


class BehaviorRequest(BaseModel):
    user_id: int
    item_id: int
    action: ActionEnum
    timestamp: int
    ab_group: str = "default"

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        import time
        if v <= 0:
            return int(time.time())
        return v


class BehaviorResponse(BaseModel):
    status: str
    message: str


class ItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = ""
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    features: Optional[Dict[str, Any]] = None
    created_at: Optional[int] = None


class ItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    features: Optional[Dict[str, Any]] = None


class ItemResponse(BaseModel):
    id: int
    title: str
    description: str
    categories: List[str]
    tags: List[str]
    features: Dict[str, Any]
    likes: int
    comments: int
    views: int
    created_at: int
    updated_at: int


class ItemListResponse(BaseModel):
    items: List[ItemResponse]
    total: int


class HealthResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    status: str
    model_ready: bool
    redis_connected: bool


class ErrorResponse(BaseModel):
    detail: str


class UserProfile(BaseModel):
    user_id: int
    preferred_categories: List[str]
    preferred_tags: List[str]
    interaction_count: int
    last_active: int
