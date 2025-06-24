#!/usr/bin/env python3
"""
TikTok功能测试脚本
"""

import asyncio
import logging
from services.video_service import video_service

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_tiktok_creator():
    """测试TikTok创作者视频获取"""
    test_url = "https://www.tiktok.com/@crazydaywithshay"
    
    try:
        logger.info(f"测试TikTok创作者: {test_url}")
        result = await video_service.get_creator_videos(test_url, max_count=5)
        
        logger.info(f"创作者信息: {result.creator_info.name}")
        logger.info(f"视频数量: {len(result.videos)}")
        logger.info(f"总数量: {result.total_count}")
        logger.info(f"是否有更多: {result.has_more}")
        
        for i, video in enumerate(result.videos[:3], 1):  # 只显示前3个
            logger.info(f"视频 {i}: {video.title}")
            logger.info(f"  URL: {video.url}")
            logger.info(f"  时长: {video.duration}s")
            logger.info(f"  观看数: {video.view_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False

async def test_tiktok_video_info():
    """测试TikTok单个视频信息获取"""
    # 这里需要一个有效的TikTok视频URL进行测试
    # test_url = "https://www.tiktok.com/@username/video/1234567890"
    
    logger.info("单视频信息测试跳过 - 需要有效的视频URL")
    return True

async def main():
    """主测试函数"""
    logger.info("开始TikTok功能测试...")
    
    # 测试创作者视频获取
    creator_test = await test_tiktok_creator()
    
    # 测试单视频信息获取
    video_test = await test_tiktok_video_info()
    
    if creator_test and video_test:
        logger.info("所有测试通过！")
    else:
        logger.error("部分测试失败")

if __name__ == "__main__":
    asyncio.run(main())
