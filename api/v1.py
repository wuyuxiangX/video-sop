from fastapi import APIRouter
from .endpoints import video, platforms, auth

router = APIRouter()

# 包含所有端点路由
router.include_router(video.router, prefix="/video", tags=["video"])
router.include_router(platforms.router, prefix="/platforms", tags=["platforms"])
router.include_router(auth.router, prefix="/auth", tags=["authentication"])
