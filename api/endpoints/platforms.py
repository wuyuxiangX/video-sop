from fastapi import APIRouter
from typing import List

from models import PlatformInfo, Platform
from services.video_service import video_service

router = APIRouter()


@router.get("/", response_model=List[PlatformInfo])
async def get_supported_platforms():
    """获取支持的平台列表"""
    platforms = [
        PlatformInfo(
            name="Bilibili",
            supported=True,
            tool="you-get",
            description="中国最大的弹幕视频网站"
        ),
        PlatformInfo(
            name="TikTok",
            supported=True,
            tool="yt-dlp",
            description="国际短视频平台"
        )
    ]
    
    return platforms


@router.get("/detect")
async def detect_platform(url: str):
    """检测视频URL的平台"""
    platform = video_service.detect_platform(url)
    
    platform_names = {
        Platform.BILIBILI: "Bilibili",
        Platform.TIKTOK: "TikTok",
        Platform.UNKNOWN: "Unknown"
    }
    
    return {
        "url": url,
        "platform": platform.value,
        "platform_name": platform_names.get(platform, "Unknown"),
        "supported": platform != Platform.UNKNOWN
    }
