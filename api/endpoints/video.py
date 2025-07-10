import urllib.parse
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import os
import asyncio
import logging
from typing import Optional

from models import (
    VideoQuality, Platform, CreatorVideosResponse, CreatorInfo
)
from services.video_service import video_service, detect_platform

router = APIRouter()
logger = logging.getLogger(__name__)



@router.post("/download")
async def download_video_stream(
    url: str = Query(..., description="视频URL，支持base64编码"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """流式代理下载视频（边下载边转发）- 支持base64编码URL"""
    logger.info(f"开始处理流式代理下载请求: {url[:50]}...")
    
    try:
        # 标准化输入（base64解码）
        normalized_url = video_service.normalize_input(url)
        logger.info(f"标准化URL完成")
        
        # 检测平台
        platform = detect_platform(normalized_url)
        logger.info(f"检测到平台: {platform}")
        
        # 使用简单的默认文件名
        import time
        timestamp = int(time.time())
        safe_filename = f"video_{timestamp}.mp4"
        encoded_filename = urllib.parse.quote(safe_filename.encode('utf-8'))
        
        # 创建流式下载生成器
        async def stream_download():
            """先下载到临时文件，然后流式传输"""
            import tempfile
            import shutil
            
            temp_dir = None
            try:
                logger.info("开始下载视频到临时文件...")
                
                # 创建临时目录
                temp_dir = tempfile.mkdtemp(dir="./temp")
                
                # 使用video_service下载
                try:
                    file_path = await video_service.download_video(normalized_url, quality)
                    logger.info(f"视频下载完成: {file_path}")
                except Exception as e:
                    logger.error(f"下载失败: {e}")
                    raise Exception(f"视频下载失败: {str(e)[:100]}")
                
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
        logger.error(f"流式代理下载出现未预期错误: {e}")
        raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")



@router.post("/creator", response_model=CreatorVideosResponse)
async def get_creator_videos_post(
    url: str = Query(..., description="创作者URL，支持base64编码"),
    max_count: int = Query(20, description="最大获取视频数量", ge=1, le=500)
):
    """获取创作者视频列表 - 支持base64编码URL"""
    logger.info(f"获取创作者视频请求: {url[:50]}...")
    
    try:
        # 标准化输入（base64解码）
        normalized_url = video_service.normalize_input(url)
        logger.info(f"标准化URL完成")
        
        # 检测平台
        platform = detect_platform(normalized_url)
        logger.info(f"检测到平台: {platform}")
        
        # 添加更严格的错误处理，避免连接重置
        try:
            creator_videos = await video_service.get_creator_videos(normalized_url, max_count)
            logger.info(f"获取视频列表成功")
            return creator_videos
        except asyncio.TimeoutError:
            logger.error(f"获取视频列表超时")
            raise HTTPException(
                status_code=408, 
                detail="请求超时，服务器响应较慢，请稍后重试"
            )
        except Exception as service_error:
            logger.error(f"video_service处理失败: {service_error}")
            # 返回一个友好的错误响应而不是让连接重置
            return CreatorVideosResponse(
                creator_info=CreatorInfo(
                    name="服务暂不可用",
                    platform=platform,
                    profile_url=normalized_url,
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
        logger.error(f"获取创作者视频出现未预期错误: {e}")
        # 最后的安全网，确保不会导致连接重置
        raise HTTPException(
            status_code=500, 
            detail="服务内部错误，请稍后重试"
        )









