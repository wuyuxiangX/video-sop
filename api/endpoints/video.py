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
async def get_video_info_post(url: str = Query(..., description="视频URL")):
    """获取视频信息 - POST版本"""
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



@router.post("/download")
async def download_video_stream(
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








@router.post("/creator", response_model=CreatorVideosResponse)
async def get_creator_videos_post(
    creator_url: str = Query(..., description="博主主页URL"),
    max_count: int = Query(20, description="最大获取视频数量", ge=1, le=500)
):
    """获取博主所有视频列表 (POST方式)"""
    try:
        # 验证URL格式
        if not creator_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="请提供有效的URL")
        
        # 添加更严格的错误处理，避免连接重置
        try:
            creator_videos = await video_service.get_creator_videos(creator_url, max_count)
            logger.info(f"获取视频列表成功: {creator_url}")
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


@router.get("/test")
async def test_get(a: str = Query(..., description="测试参数")):
    """GET测试端点"""
    logger.info(f"GET测试端点被调用: a={a}")
    return a


@router.post("/test")
async def test_post(a: str = Query(..., description="测试参数")):
    """POST测试端点"""
    logger.info(f"POST测试端点被调用: a={a}")
    return a


@router.post("/test2")
async def test2_post(a: str = Query(..., description="测试参数")):
    """POST测试端点2 - 返回模拟的CreatorVideosResponse"""
    logger.info(f"POST测试端点2被调用: a={a}")
    
    # 返回固定的模拟数据
    return {
        "creator_info": {
            "name": "crazydaywithshay",
            "platform": "tiktok",
            "profile_url": "https://www.tiktok.com/@crazydaywithshay",
            "avatar": None,
            "description": None,
            "follower_count": None,
            "video_count": None
        },
        "videos": [
            {
                "title": "Let them… think whateverrrrr they want #f#fypf#foryoupagex#xyzbcab#bl...",
                "url": "https://www.tiktok.com/@crazydaywithshay/video/7519292008230325535",
                "thumbnail": None,
                "duration": 9,
                "upload_date": "20250623",
                "view_count": 672,
                "bv_id": None,
                "description": None
            }
        ],
        "total_count": 1,
        "has_more": False,
        "next_page": None
    }






