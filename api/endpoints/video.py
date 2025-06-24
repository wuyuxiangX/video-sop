import re
import urllib.parse
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
import os
import asyncio
import logging
from typing import Optional

from models import (
    VideoInfo, VideoDownloadResponse, ErrorResponse, 
    VideoQuality, Platform, CreatorVideosResponse, CreatorInfo, CreatorVideoItem
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
async def download_video_stream_proxy(
    url: str = Query(..., description="视频URL"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """流式代理下载视频（边下载边转发）"""
    logger.info(f"开始处理流式代理下载请求: {url}, 质量: {quality}")
    
    try:
        # 首先获取视频信息
        logger.info("获取视频信息...")
        try:
            video_info = await asyncio.wait_for(
                video_service.get_video_info(url), 
                timeout=60  # 1分钟获取信息超时
            )
            logger.info(f"视频信息获取成功: {video_info.title}")
        except asyncio.TimeoutError:
            logger.error(f"获取视频信息超时: {url}")
            raise HTTPException(status_code=408, detail="获取视频信息超时，请稍后重试")
        except Exception as e:
            logger.error(f"获取视频信息失败: {url}, 错误: {e}")
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
            """真正的流式代理下载：边下载边转发"""
            process = None
            try:
                logger.info("启动yt-dlp流式下载进程...")
                
                # 检测平台并构建命令
                platform = video_service.detect_platform(url)
                if platform.value == "tiktok":
                    cmd = [
                        "yt-dlp",
                        "-f", "worst[ext=mp4]/worst",  # 优先mp4格式
                        "--socket-timeout", "20",
                        "--retries", "2",
                        "--no-warnings",
                        "--no-playlist",
                        "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                        "-o", "-",  # 输出到stdout
                        url
                    ]
                else:
                    # Bilibili使用you-get
                    cmd = ["you-get", "-o", "-", url]
                
                logger.info("启动下载进程进行流式传输...")
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                if process.stdout is None:
                    raise Exception("无法获取进程stdout")
                if process.stderr is None:
                    raise Exception("无法获取进程stderr")
                
                # 实时读取并转发数据
                bytes_transferred = 0
                chunk_count = 0
                
                while True:
                    # 读取数据块
                    try:
                        chunk = await asyncio.wait_for(
                            process.stdout.read(8192),  # 8KB chunks
                            timeout=30  # 30秒读取超时
                        )
                    except asyncio.TimeoutError:
                        logger.error("读取数据块超时")
                        break
                    
                    if not chunk:
                        # 数据读取完毕
                        logger.info("数据流结束")
                        break
                    
                    bytes_transferred += len(chunk)
                    chunk_count += 1
                    
                    # 每传输1MB记录一次日志
                    if chunk_count % 128 == 0:  # 128 * 8KB = 1MB
                        logger.info(f"已传输: {bytes_transferred / 1024 / 1024:.1f} MB")
                    
                    yield chunk
                
                # 等待进程结束
                await process.wait()
                
                if process.returncode != 0:
                    stderr_output = await process.stderr.read()
                    error_msg = stderr_output.decode('utf-8', errors='ignore')
                    logger.error(f"yt-dlp进程失败，返回码: {process.returncode}, 错误: {error_msg[:200]}")
                else:
                    logger.info(f"流式传输完成，总计传输: {bytes_transferred / 1024 / 1024:.1f} MB")
                    
            except Exception as e:
                logger.error(f"流式下载过程中出错: {e}")
                if process and process.returncode is None:
                    try:
                        process.kill()
                        await process.wait()
                    except:
                        pass
                raise HTTPException(status_code=500, detail=f"流式下载失败: {str(e)[:100]}")
        
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
        logger.error(f"流式代理下载出现未预期错误 {url}: {e}")
        raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")


@router.get("/download-url")
async def get_download_url(
    url: str = Query(..., description="视频URL"),
    quality: VideoQuality = Query(VideoQuality.WORST, description="视频质量，默认最低质量")
):
    """获取视频下载相关信息"""
    try:
        platform = video_service.detect_platform(url)
        if platform == Platform.UNKNOWN:
            raise HTTPException(status_code=400, detail="Unsupported platform")
        
        # 获取视频信息
        video_info = await video_service.get_video_info(url)
        
        return {
            "video_info": video_info,
            "message": "Use /download endpoint for streaming download",
            "platform": platform.value,
            "download_url": f"/api/v1/video/download?url={url}&quality={quality.value}"
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


@router.get("/test-creator")
async def test_creator_endpoint(
    creator_url: str = Query(..., description="博主主页URL"),
    max_count: int = Query(20, description="最大获取视频数量", ge=1, le=500)
):
    """测试创作者端点（不调用yt-dlp）"""
    try:
        # 模拟返回，不实际调用yt-dlp
        test_creator = CreatorInfo(
            name="测试博主",
            platform=Platform.TIKTOK,
            profile_url=creator_url,
            description="这是一个测试响应，用于验证API结构"
        )
        
        test_videos = [
            CreatorVideoItem(
                title=f"测试视频 {i+1}",
                url=f"https://test.com/video/{i+1}",
                description="测试视频描述"
            ) for i in range(min(max_count, 3))
        ]
        
        return CreatorVideosResponse(
            creator_info=test_creator,
            videos=test_videos,
            total_count=len(test_videos),
            has_more=False
        )
        
    except Exception as e:
        logger.error(f"测试端点错误: {e}")
        raise HTTPException(status_code=500, detail=f"测试端点错误: {str(e)}")



