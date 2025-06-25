from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
from enum import Enum


class Platform(str, Enum):
    BILIBILI = "bilibili"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


class VideoQuality(str, Enum):
    BEST = "best"
    WORST = "worst"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VideoInfo(BaseModel):
    """视频信息模型"""
    title: str
    duration: Optional[int] = None
    platform: Platform
    url: str
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    formats: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None  # 支持字典和列表格式
    
    @field_validator('duration', 'view_count')
    @classmethod
    def validate_numeric_fields(cls, v):
        """验证数值字段，将浮点数转换为整数，处理各种数值类型"""
        if v is None:
            return None
        try:
            # 如果是数字类型，转换为整数
            if isinstance(v, (int, float)):
                if str(v).lower() in ['nan', 'inf', '-inf']:
                    return None
                return int(float(v))
            # 如果是字符串，尝试转换
            elif isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
            else:
                return None
        except (ValueError, TypeError, OverflowError):
            return None
    
    @field_validator('formats')
    @classmethod
    def validate_formats(cls, v):
        # 允许None、字典或列表
        if v is None or isinstance(v, (dict, list)):
            return v
        return None


class CreatorInfo(BaseModel):
    """博主信息模型"""
    name: str
    platform: Platform
    profile_url: str
    avatar: Optional[str] = None
    description: Optional[str] = None
    follower_count: Optional[int] = None
    video_count: Optional[int] = None
    
    @field_validator('follower_count', 'video_count')
    @classmethod
    def validate_counts(cls, v):
        """验证数量字段，将浮点数转换为整数"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)  # 将浮点数转换为整数
        return None


class CreatorVideoItem(BaseModel):
    """博主视频列表项模型"""
    title: str
    url: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    bv_id: Optional[str] = None  # B站特有
    description: Optional[str] = None  # 视频描述
    
    @field_validator('duration', 'view_count')
    @classmethod
    def validate_numeric_fields(cls, v):
        """验证数值字段，将浮点数转换为整数，处理各种数值类型"""
        if v is None:
            return None
        try:
            # 如果是数字类型，转换为整数
            if isinstance(v, (int, float)):
                if str(v).lower() in ['nan', 'inf', '-inf']:
                    return None
                return int(float(v))
            # 如果是字符串，尝试转换
            elif isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
            else:
                return None
        except (ValueError, TypeError, OverflowError):
            return None


class CreatorVideosResponse(BaseModel):
    """博主视频列表响应模型"""
    creator_info: CreatorInfo
    videos: List[CreatorVideoItem]
    total_count: int
    has_more: bool = False
    next_page: Optional[str] = None
    
    
class VideoDownloadRequest(BaseModel):
    """视频下载请求模型"""
    url: str = Field(..., description="视频URL")
    quality: VideoQuality = Field(VideoQuality.WORST, description="视频质量，默认最低质量")
    
    
class VideoDownloadResponse(BaseModel):
    """视频下载响应模型"""
    success: bool
    message: str
    video_info: Optional[VideoInfo] = None
    download_url: Optional[str] = None
    
    
class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str
    detail: Optional[str] = None
    
    
class PlatformInfo(BaseModel):
    """平台信息模型"""
    name: str
    supported: bool
    tool: str
    description: str



