import re
import urllib.parse
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
import os
import aiofiles
import asyncio
import logging
from typing import Optional

from models import (
    VideoInfo, VideoDownloadResponse, ErrorResponse, 
    VideoQuality, Platform, CreatorVideosResponse, CreatorInfo
)
from services.video_service import video_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/info", response_model=VideoInfo)
async def get_video_info(url: str = Query(..., description="视频URL")):
    """获取视频信息"""
    try:
        # 添加更严格的错误处理，避免连接重置
        try:
            video_info = await video_service.get_video_info(url)
            return video_info
        except asyncio.TimeoutError:
            logger.error(f"获取视频信息超时: {url}")
            raise HTTPException(
                status_code=408, 
                detail="请求超时，视频服务器响应较慢，请稍后重试"
            )
        except Exception as service_error:
            logger.error(f"Failed to get video info for {url}: {service_error}")
            # 如果是TikTok URL，提供特殊的错误处理
            if "tiktok.com" in url.lower():
                raise HTTPException(
                    status_code=503, 
                    detail=f"TikTok服务暂不可用: {str(service_error)[:100]}"
                )
            else:
                raise HTTPException(status_code=400, detail=str(service_error))
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"获取视频信息出现未预期错误 {url}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="服务内部错误，请稍后重试"
        )


@router.get("/download")
async def download_video_stream(
    url: str = Query(..., description="视频URL"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """流式下载视频"""
    try:
        # 获取视频信息
        video_info = await video_service.get_video_info(url)
        
        # 下载视频文件
        file_path = await video_service.download_video(url, quality)
        
        # 获取文件信息
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # 清理文件名，确保安全，处理中文字符
        def clean_filename(title):
            """清理文件名，移除不安全字符并处理中文"""
            # 移除不安全字符
            cleaned = re.sub(r'[<>:"/\\|?*]', '_', title)
            # 限制长度
            if len(cleaned) > 100:
                cleaned = cleaned[:100]
            return cleaned
        
        safe_title = clean_filename(video_info.title)
        file_ext = os.path.splitext(filename)[1]
        safe_filename = f"{safe_title}{file_ext}"
        
        # 对文件名进行URL编码以处理中文字符
        encoded_filename = urllib.parse.quote(safe_filename.encode('utf-8'))
        
        async def iterfile():
            """异步文件迭代器"""
            try:
                async with aiofiles.open(file_path, 'rb') as file:
                    while chunk := await file.read(8192):  # 8KB chunks
                        yield chunk
            finally:
                # 下载完成后清理临时文件
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    # 清理临时目录
                    temp_dir = os.path.dirname(file_path)
                    if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup file {file_path}: {cleanup_error}")
        
        # 返回流式响应
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(file_size)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to download video {url}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/download-url")
async def get_download_url(
    url: str = Query(..., description="视频URL"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """获取视频直接下载链接（如果支持）"""
    try:
        platform = video_service.detect_platform(url)
        if platform == Platform.UNKNOWN:
            raise HTTPException(status_code=400, detail="Unsupported platform")
        
        # 对于某些平台，我们可以直接返回下载链接而不需要先下载
        # 这里可以根据需要实现直接链接获取逻辑
        video_info = await video_service.get_video_info(url)
        
        return {
            "video_info": video_info,
            "message": "Use /download endpoint for streaming download",
            "platform": platform.value
        }
        
    except Exception as e:
        logger.error(f"Failed to get download URL for {url}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/download", response_model=VideoDownloadResponse)
async def download_video_async(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="视频URL"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """异步下载视频（返回下载状态）"""
    try:
        # 获取视频信息
        video_info = await video_service.get_video_info(url)
        
        # 这里可以实现异步下载任务
        # 实际生产环境中可能需要使用任务队列如Celery
        
        return VideoDownloadResponse(
            success=True,
            message="Video download initiated",
            video_info=video_info,
            download_url=f"/api/v1/video/download?url={url}&quality={quality.value}"
        )
        
    except Exception as e:
        logger.error(f"Failed to initiate download for {url}: {e}")
        return VideoDownloadResponse(
            success=False,
            message=str(e)
        )


@router.get("/creator", response_model=CreatorVideosResponse)
async def get_creator_videos_get(
    creator_url: str = Query(..., description="博主主页URL"),
    max_count: int = Query(20, description="最大获取视频数量", ge=1, le=500)
):
    """获取博主所有视频列表 (GET方式)"""
    try:
        # 验证URL格式
        if not creator_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="请提供有效的URL")
        
        # 添加更严格的错误处理，避免连接重置
        try:
            creator_videos = await video_service.get_creator_videos(creator_url, max_count)
            return creator_videos
        except asyncio.TimeoutError:
            logger.error(f"获取视频列表超时: {creator_url}")
            raise HTTPException(
                status_code=408, 
                detail="请求超时，TikTok服务器响应较慢，请稍后重试"
            )
        except Exception as service_error:
            logger.error(f"video_service处理失败: {creator_url}, 错误: {service_error}")
            # 返回一个友好的错误响应而不是让连接重置
            return CreatorVideosResponse(
                creator_info=CreatorInfo(
                    name="服务暂不可用",
                    platform=Platform.TIKTOK,
                    profile_url=creator_url,
                    description=f"抱歉，当前无法获取视频列表。错误信息: {str(service_error)[:100]}"
                ),
                videos=[],
                total_count=0,
                has_more=False
            )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"获取创作者视频出现未预期错误 {creator_url}: {e}")
        # 最后的安全网，确保不会导致连接重置
        raise HTTPException(
            status_code=500, 
            detail="服务内部错误，请稍后重试"
        )



