import re
import urllib.parse
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import os
import asyncio
import logging
from typing import Optional

from models import (
    VideoInfo, VideoQuality, Platform, CreatorVideosResponse, CreatorInfo, CreatorVideoItem
)
from services.video_service import video_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/info", response_model=VideoInfo)
async def get_video_info_post(video_path: str = Query(..., description="视频路径，例如: @crazydaywithshay/video/7517350403659369759")):
    """获取视频信息 - 支持简化路径格式"""
    logger.info(f"获取视频信息请求: {video_path}")
    
    try:
        # 规范化输入为完整URL
        full_url = video_service.normalize_tiktok_input(video_path)
        logger.info(f"规范化URL: {video_path} -> {full_url}")
        
        # 添加更严格的错误处理，避免连接重置
        try:
            video_info = await video_service.get_video_info(full_url)
            return video_info
        except asyncio.TimeoutError:
            logger.error(f"获取视频信息超时: {full_url}")
            raise HTTPException(
                status_code=408, 
                detail="请求超时，视频服务器响应较慢，请稍后重试"
            )
        except Exception as service_error:
            logger.error(f"Failed to get video info for {full_url}: {service_error}")
            # 如果是TikTok URL，提供特殊的错误处理
            if "tiktok.com" in full_url.lower():
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
        logger.error(f"获取视频信息出现未预期错误 {video_path}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="服务内部错误，请稍后重试"
        )



@router.post("/download")
async def download_video_stream(
    video_path: str = Query(..., description="视频路径，例如: @crazydaywithshay/video/7517350403659369759"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """流式代理下载视频（边下载边转发）- 支持简化路径格式"""
    logger.info(f"开始处理流式代理下载请求: {video_path}, 质量: {quality}")
    
    try:
        # 规范化输入为完整URL
        full_url = video_service.normalize_tiktok_input(video_path)
        logger.info(f"规范化URL: {video_path} -> {full_url}")
        
        # 首先获取视频信息
        logger.info("获取视频信息...")
        try:
            video_info = await asyncio.wait_for(
                video_service.get_video_info(full_url), 
                timeout=60  # 1分钟获取信息超时
            )
            logger.info(f"视频信息获取成功: {video_info.title}")
        except asyncio.TimeoutError:
            logger.error(f"获取视频信息超时: {full_url}")
            raise HTTPException(status_code=408, detail="获取视频信息超时，请稍后重试")
        except Exception as e:
            logger.error(f"获取视频信息失败: {full_url}, 错误: {e}")
            raise HTTPException(status_code=400, detail=f"无法获取视频信息: {str(e)[:100]}")
        
        # 清理文件名，确保安全，处理中文字符
        def clean_filename(title):
            """清理文件名，移除不安全字符并处理中文"""
            cleaned = re.sub(r'[<>:"/\\|?*]', '_', title)
            if len(cleaned) > 80:
                cleaned = cleaned[:80]
            return cleaned
        
        safe_title = clean_filename(video_info.title)
        safe_filename = f"{safe_title}.mp4"
        encoded_filename = urllib.parse.quote(safe_filename.encode('utf-8'))
        
        # 创建流式下载生成器
        async def stream_download():
            """先下载到临时文件，然后流式传输"""
            import tempfile
            import os
            import shutil
            
            temp_dir = None
            try:
                logger.info("开始下载视频到临时文件...")
                
                # 创建临时目录
                temp_dir = tempfile.mkdtemp(dir="./temp")
                
                # 检测平台并直接使用video_service下载
                platform = video_service.detect_platform(full_url)
                logger.info(f"检测到平台: {platform}")
                
                if platform in [Platform.TIKTOK, Platform.BILIBILI, Platform.YOUTUBE]:
                    # 统一使用 video_service 的下载功能（所有平台都使用yt-dlp）
                    try:
                        file_path = await video_service.download_video(full_url, quality)
                        logger.info(f"{platform.value}视频下载完成: {file_path}")
                    except Exception as e:
                        logger.error(f"{platform.value}下载失败: {e}")
                        raise Exception(f"{platform.value}视频下载失败: {str(e)[:100]}")
                else:
                    raise Exception(f"不支持的平台: {platform.value}")
                
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    raise Exception(f"下载的文件不存在: {file_path}")
                
                file_size = os.path.getsize(file_path)
                logger.info(f"开始流式传输文件: {file_path}, 大小: {file_size} bytes")
                
                # 流式读取文件并传输
                with open(file_path, 'rb') as f:
                    bytes_transferred = 0
                    chunk_size = 8192  # 8KB chunks
                    
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        
                        bytes_transferred += len(chunk)
                        
                        # 每传输1MB记录一次日志
                        if bytes_transferred % (1024 * 1024) == 0:
                            logger.info(f"已传输: {bytes_transferred / 1024 / 1024:.1f} MB")
                        
                        yield chunk
                
                logger.info(f"流式传输完成，总计传输: {bytes_transferred / 1024 / 1024:.1f} MB")
                    
            except Exception as e:
                logger.error(f"下载过程中出错: {e}")
                raise HTTPException(status_code=500, detail=f"下载失败: {str(e)[:100]}")
            finally:
                # 清理临时文件
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                        logger.info(f"清理临时目录: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"清理临时目录失败: {e}")
        
        # 设置响应头（不包含Content-Length，因为是流式传输）
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Type": "application/octet-stream",
            "Transfer-Encoding": "chunked"  # 明确指定分块传输
        }
        
        logger.info(f"开始流式代理传输，文件名: {safe_filename}")
        
        return StreamingResponse(
            stream_download(),
            media_type="application/octet-stream",
            headers=headers
        )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"流式代理下载出现未预期错误 {video_path}: {e}")
        raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")



@router.post("/creator", response_model=CreatorVideosResponse)
async def get_creator_videos_post(
    username: str = Query(..., description="TikTok用户名，例如: @crazydaywithshay 或 crazydaywithshay"),
    max_count: int = Query(20, description="最大获取视频数量", ge=1, le=500)
):
    """获取博主所有视频列表 - 支持简化用户名格式"""
    logger.info(f"获取创作者视频请求: {username}")
    
    try:
        # 规范化输入为完整URL
        full_url = video_service.normalize_tiktok_input(username)
        logger.info(f"规范化URL: {username} -> {full_url}")
        
        # 添加更严格的错误处理，避免连接重置
        try:
            creator_videos = await video_service.get_creator_videos(full_url, max_count)
            logger.info(f"获取视频列表成功: {full_url}")
            return creator_videos
        except asyncio.TimeoutError:
            logger.error(f"获取视频列表超时: {full_url}")
            raise HTTPException(
                status_code=408, 
                detail="请求超时，TikTok服务器响应较慢，请稍后重试"
            )
        except Exception as service_error:
            logger.error(f"video_service处理失败: {full_url}, 错误: {service_error}")
            # 返回一个友好的错误响应而不是让连接重置
            return CreatorVideosResponse(
                creator_info=CreatorInfo(
                    name="服务暂不可用",
                    platform=Platform.TIKTOK,
                    profile_url=full_url,
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
        logger.error(f"获取创作者视频出现未预期错误 {username}: {e}")
        # 最后的安全网，确保不会导致连接重置
        raise HTTPException(
            status_code=500, 
            detail="服务内部错误，请稍后重试"
        )









