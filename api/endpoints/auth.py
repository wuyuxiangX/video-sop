import os
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

COOKIE_FILE_PATH = "./cookies.txt"
COOKIE_BACKUP_PATH = "./cookies_backup.txt"

@router.post("/upload-cookies")
async def upload_cookies(cookie_file: UploadFile = File(..., description="YouTube cookies.txt文件")):
    """
    上传YouTube cookies文件
    支持Netscape格式的cookies.txt文件
    """
    logger.info(f"收到cookie文件上传请求: {cookie_file.filename}")
    
    try:
        # 验证文件类型
        if not cookie_file.filename or not cookie_file.filename.endswith('.txt'):
            raise HTTPException(
                status_code=400, 
                detail="请上传.txt格式的cookie文件"
            )
        
        # 读取文件内容
        content = await cookie_file.read()
        
        # 验证文件不为空
        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="cookie文件不能为空"
            )
        
        # 解码内容
        try:
            cookie_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="cookie文件编码错误，请确保文件为UTF-8编码"
            )
        
        # 基本格式验证
        if not _validate_cookie_format(cookie_content):
            raise HTTPException(
                status_code=400,
                detail="cookie文件格式错误，请确保是Netscape格式的cookies.txt文件"
            )
        
        # 备份现有的cookie文件（如果存在）
        if os.path.exists(COOKIE_FILE_PATH):
            try:
                with open(COOKIE_BACKUP_PATH, 'w', encoding='utf-8') as backup_file:
                    with open(COOKIE_FILE_PATH, 'r', encoding='utf-8') as current_file:
                        backup_file.write(current_file.read())
                logger.info(f"已备份现有cookie文件到: {COOKIE_BACKUP_PATH}")
            except Exception as e:
                logger.warning(f"备份cookie文件失败: {e}")
        
        # 保存新的cookie文件
        with open(COOKIE_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(cookie_content)
        
        # 设置文件权限
        os.chmod(COOKIE_FILE_PATH, 0o644)
        
        file_size = os.path.getsize(COOKIE_FILE_PATH)
        logger.info(f"成功保存cookie文件: {COOKIE_FILE_PATH}, 大小: {file_size} bytes")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "cookie文件上传成功",
                "file_size": file_size,
                "timestamp": datetime.now().isoformat(),
                "note": "新的cookie配置将在下次请求时生效"
            }
        )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"上传cookie文件时发生错误: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部错误: {str(e)}"
        )

@router.get("/cookie-status")
async def get_cookie_status():
    """
    检查当前cookie文件状态
    """
    try:
        status = {
            "cookie_file_exists": False,
            "file_size": 0,
            "last_modified": None,
            "backup_exists": False,
            "is_readable": False,
            "estimated_cookie_count": 0
        }
        
        # 检查主cookie文件
        if os.path.exists(COOKIE_FILE_PATH):
            status["cookie_file_exists"] = True
            
            try:
                # 文件大小
                status["file_size"] = os.path.getsize(COOKIE_FILE_PATH)
                
                # 修改时间
                mtime = os.path.getmtime(COOKIE_FILE_PATH)
                status["last_modified"] = datetime.fromtimestamp(mtime).isoformat()
                
                # 检查是否可读并统计cookie数量
                with open(COOKIE_FILE_PATH, 'r', encoding='utf-8') as f:
                    content = f.read()
                    status["is_readable"] = True
                    
                    # 估算cookie数量（非注释行）
                    lines = content.split('\n')
                    cookie_lines = [line for line in lines 
                                  if line.strip() and not line.strip().startswith('#')]
                    status["estimated_cookie_count"] = len(cookie_lines)
                    
            except Exception as e:
                logger.warning(f"读取cookie文件时出错: {e}")
                status["is_readable"] = False
        
        # 检查备份文件
        if os.path.exists(COOKIE_BACKUP_PATH):
            status["backup_exists"] = True
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "status": status,
                "recommendations": _get_recommendations(status)
            }
        )
        
    except Exception as e:
        logger.error(f"检查cookie状态时发生错误: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"无法检查cookie状态: {str(e)}"
        )

@router.delete("/cookies")
async def delete_cookies():
    """
    删除当前的cookie文件
    """
    try:
        deleted_files = []
        
        # 删除主cookie文件
        if os.path.exists(COOKIE_FILE_PATH):
            os.remove(COOKIE_FILE_PATH)
            deleted_files.append("cookies.txt")
            logger.info(f"已删除cookie文件: {COOKIE_FILE_PATH}")
        
        # 可选：删除备份文件
        if os.path.exists(COOKIE_BACKUP_PATH):
            os.remove(COOKIE_BACKUP_PATH)
            deleted_files.append("cookies_backup.txt")
            logger.info(f"已删除备份文件: {COOKIE_BACKUP_PATH}")
        
        if not deleted_files:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "没有找到需要删除的cookie文件"
                }
            )
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"成功删除文件: {', '.join(deleted_files)}",
                "deleted_files": deleted_files,
                "note": "下次请求将使用无cookie模式"
            }
        )
        
    except Exception as e:
        logger.error(f"删除cookie文件时发生错误: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"删除cookie文件失败: {str(e)}"
        )

@router.post("/restore-cookies")
async def restore_cookies_from_backup():
    """
    从备份恢复cookie文件
    """
    try:
        if not os.path.exists(COOKIE_BACKUP_PATH):
            raise HTTPException(
                status_code=404,
                detail="未找到备份文件"
            )
        
        # 读取备份文件
        with open(COOKIE_BACKUP_PATH, 'r', encoding='utf-8') as backup_file:
            backup_content = backup_file.read()
        
        # 恢复到主文件
        with open(COOKIE_FILE_PATH, 'w', encoding='utf-8') as main_file:
            main_file.write(backup_content)
        
        # 设置权限
        os.chmod(COOKIE_FILE_PATH, 0o644)
        
        file_size = os.path.getsize(COOKIE_FILE_PATH)
        logger.info(f"成功从备份恢复cookie文件，大小: {file_size} bytes")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "成功从备份恢复cookie文件",
                "file_size": file_size,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢复cookie文件时发生错误: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"恢复cookie文件失败: {str(e)}"
        )

def _validate_cookie_format(content: str) -> bool:
    """
    验证cookie文件格式
    检查是否符合Netscape格式
    """
    lines = content.split('\n')
    
    # 至少应该有一些非空行
    non_empty_lines = [line for line in lines if line.strip()]
    if len(non_empty_lines) == 0:
        return False
    
    # 检查是否有YouTube相关的cookie
    has_youtube_cookies = False
    cookie_line_count = 0
    
    for line in lines:
        line = line.strip()
        
        # 跳过空行和注释
        if not line or line.startswith('#'):
            continue
        
        # 分割cookie行（Netscape格式通常是tab分隔的7个字段）
        parts = line.split('\t')
        if len(parts) >= 6:  # 至少6个字段
            cookie_line_count += 1
            
            # 检查域名字段（第一个字段）
            domain = parts[0]
            if 'youtube.com' in domain or 'google.com' in domain:
                has_youtube_cookies = True
    
    # 验证条件：至少有一些cookie行，并且最好有YouTube相关的cookie
    return cookie_line_count > 0 and has_youtube_cookies

def _get_recommendations(status: dict) -> list:
    """
    根据当前状态生成建议
    """
    recommendations = []
    
    if not status["cookie_file_exists"]:
        recommendations.append("建议上传cookie文件以解决YouTube认证问题")
    elif status["file_size"] == 0:
        recommendations.append("cookie文件为空，请重新上传有效的cookie文件")
    elif not status["is_readable"]:
        recommendations.append("cookie文件不可读，请检查文件权限或重新上传")
    elif status["estimated_cookie_count"] == 0:
        recommendations.append("cookie文件中没有找到有效的cookie，请确认文件格式")
    elif status["estimated_cookie_count"] < 5:
        recommendations.append("cookie数量较少，可能影响认证效果")
    else:
        recommendations.append("cookie配置看起来正常")
    
    if status["backup_exists"]:
        recommendations.append("存在备份文件，如有问题可以使用restore接口恢复")
    
    return recommendations 