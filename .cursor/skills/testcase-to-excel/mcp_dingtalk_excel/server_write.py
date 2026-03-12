#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钉钉Excel写入 MCP 服务器
提供钉钉Excel表格数据写入功能
"""

from typing import Annotated, Optional, Dict, Any, List
import os
import time
import json
import asyncio
import re
import traceback
import logging
from pathlib import Path

import httpx
from mcp.shared.exceptions import McpError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    ErrorData,
    Tool,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    TextContent,
)
from pydantic import BaseModel, Field

# ==================== 常量定义 ====================
API_BASE_URL = "https://api.dingtalk.com/v1.0/doc"
TOKEN_API_URL = "http://gaia-hg.momo.com/ding/excel/token"
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36'
DEFAULT_TIMEOUT = 30.0

# 从环境变量获取默认值
DEFAULT_AEGIS_KEY = os.getenv("DINGTALK_AEGIS_KEY", "8e052add-cbef-41aa-aac3-9c16ed1cf4b7")
DEFAULT_AEGIS_SECRET = os.getenv("DINGTALK_AEGIS_SECRET", "17764e8a-655f-4335-927e-4e1205bc49e0")
DEFAULT_WORKID = os.getenv("DINGTALK_WORKID", "110010")

# HTTP请求通用Headers
COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "content-type": "application/json",
}

# 缓存文件路径
CACHE_FILE = os.path.join(os.path.dirname(__file__), '.dingtalk_token_cache.json')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 错误处理辅助函数 ====================
def format_http_error(e: httpx.HTTPError, url: str = "", context: str = "") -> str:
    """
    格式化HTTP错误信息，输出详细信息
    
    Args:
        e: HTTP异常对象
        url: 请求的URL（可选）
        context: 上下文信息（可选）
        
    Returns:
        格式化的错误信息字符串
    """
    error_parts = []
    
    if context:
        error_parts.append(f"【上下文】{context}")
    
    if url:
        error_parts.append(f"【请求URL】{url}")
    
    error_parts.append(f"【错误类型】{type(e).__name__}")
    error_parts.append(f"【错误消息】{str(e)}")
    
    # 如果是HTTPStatusError，获取更多信息
    if isinstance(e, httpx.HTTPStatusError):
        response = e.response
        error_parts.append(f"【HTTP状态码】{response.status_code}")
        error_parts.append(f"【请求方法】{e.request.method if e.request else '未知'}")
        
        # 尝试获取响应内容
        try:
            response_text = response.text
            # 限制响应内容长度，避免过长
            if len(response_text) > 1000:
                response_text = response_text[:1000] + "... (内容已截断)"
            error_parts.append(f"【响应内容】{response_text}")
        except:
            try:
                error_parts.append(f"【响应内容】{response.content[:500]}")
            except:
                pass
    
    return "\n".join(error_parts)


def format_exception(e: Exception, context: str = "") -> str:
    """
    格式化异常信息，输出详细信息
    
    Args:
        e: 异常对象
        context: 上下文信息（可选）
        
    Returns:
        格式化的错误信息字符串
    """
    error_parts = []
    
    if context:
        error_parts.append(f"【上下文】{context}")
    
    error_parts.append(f"【异常类型】{type(e).__name__}")
    error_parts.append(f"【异常消息】{str(e)}")
    
    # 获取堆栈跟踪（限制长度）
    try:
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        tb_text = "".join(tb_lines)
        # 限制堆栈跟踪长度
        if len(tb_text) > 2000:
            tb_text = tb_text[:2000] + "... (堆栈跟踪已截断)"
        error_parts.append(f"【堆栈跟踪】\n{tb_text}")
    except:
        pass
    
    return "\n".join(error_parts)


# ==================== 数据模型 ====================
class WriteSheetDataRequest(BaseModel):
    """写入Excel表格数据请求参数"""
    url: Annotated[
        str,
        Field(description="钉钉Excel的完整URL，例如：https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r")
    ]
    sheetname: Annotated[
        Optional[str],
        Field(description="Excel表格中的Sheet名称（可选，未提供则使用第一个Sheet）", default=None)
    ]
    data: Annotated[
        List[List[Any]],
        Field(description="要写入的数据，二维数组格式，例如：[['姓名', '年龄'], ['张三', 25]]")
    ]
    startRow: Annotated[
        Optional[int],
        Field(description="起始行号（从1开始，默认为1）", default=1)
    ]
    startColumn: Annotated[
        Optional[int],
        Field(description="起始列号（从1开始，默认为1）", default=1)
    ]
    aegisKey: Annotated[
        Optional[str],
        Field(description="Aegis密钥（可选，未提供则使用环境变量DINGTALK_AEGIS_KEY）", default=None)
    ]
    aegisSecret: Annotated[
        Optional[str],
        Field(description="Aegis密钥Secret（可选，未提供则使用环境变量DINGTALK_AEGIS_SECRET）", default=None)
    ]
    workid: Annotated[
        Optional[str],
        Field(description="工作ID（可选，未提供则使用环境变量DINGTALK_WORKID）", default=None)
    ]


class DeleteRowRequest(BaseModel):
    """删除指定序号的行请求参数"""
    url: Annotated[
        str,
        Field(description="钉钉Excel的完整URL，例如：https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r")
    ]
    seqNumber: Annotated[
        int,
        Field(description="要删除的序号（第一列的序号值）")
    ]
    sheetname: Annotated[
        Optional[str],
        Field(description="Excel表格中的Sheet名称（可选，未提供则使用第一个Sheet）", default=None)
    ]
    aegisKey: Annotated[
        Optional[str],
        Field(description="Aegis密钥（可选，未提供则使用环境变量DINGTALK_AEGIS_KEY）", default=None)
    ]
    aegisSecret: Annotated[
        Optional[str],
        Field(description="Aegis密钥Secret（可选，未提供则使用环境变量DINGTALK_AEGIS_SECRET）", default=None)
    ]
    workid: Annotated[
        Optional[str],
        Field(description="工作ID（可选，未提供则使用环境变量DINGTALK_WORKID）", default=None)
    ]


class AddRowRequest(BaseModel):
    """在表格末尾添加新行请求参数"""
    url: Annotated[
        str,
        Field(description="钉钉Excel的完整URL，例如：https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r")
    ]
    rowData: Annotated[
        List[Any],
        Field(description="要添加的行数据，一维数组格式，例如：['12', '问题', '答案']。第一个元素通常是序号")
    ]
    sheetname: Annotated[
        Optional[str],
        Field(description="Excel表格中的Sheet名称（可选，未提供则使用第一个Sheet）", default=None)
    ]
    aegisKey: Annotated[
        Optional[str],
        Field(description="Aegis密钥（可选，未提供则使用环境变量DINGTALK_AEGIS_KEY）", default=None)
    ]
    aegisSecret: Annotated[
        Optional[str],
        Field(description="Aegis密钥Secret（可选，未提供则使用环境变量DINGTALK_AEGIS_SECRET）", default=None)
    ]
    workid: Annotated[
        Optional[str],
        Field(description="工作ID（可选，未提供则使用环境变量DINGTALK_WORKID）", default=None)
    ]


# ==================== Token 缓存管理 ====================
def is_invalid_auth_error(e: Exception) -> bool:
    """检测是否为钉钉 access_token 失效错误"""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            r = e.response.json()
            return (
                r.get('code') == 'InvalidAuthentication'
                or '不合法的access_token' in str(r.get('message', ''))
                or 'access_token' in str(r.get('message', '')).lower()
            )
        except Exception:
            return False
    return False


def clear_token_cache(aegisKey: str, aegisSecret: str, workid: str) -> None:
    """清除指定 key 的 token 缓存，用于 token 被钉钉服务端失效时强制重新获取"""
    cache_key = f"{workid}_{aegisKey}"
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            if cache_key in cache_data:
                del cache_data[cache_key]
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2)
                logger.info(f"已清除过期的 token 缓存: {cache_key}")
        except Exception as e:
            logger.warning(f"清除 token 缓存失败: {e}")


# ==================== 工具函数 ====================
def extract_workbook_id_from_url(url: str) -> str:
    """
    从完整URL中提取workbookId（node ID）
    
    Args:
        url: 钉钉Excel的完整URL
        
    Returns:
        提取的workbookId（node ID）
        
    Raises:
        McpError: 当无法从URL中提取workbookId时
    """
    # 匹配 /i/nodes/ 后面的node ID
    match = re.search(r'/i/nodes/([^/?]+)', url)
    if match:
        return match.group(1)
    
    # 匹配编辑页URL中的dentryKey参数（优先）
    match = re.search(r'dentryKey=([^&]+)', url)
    if match:
        return match.group(1)
    
    # 匹配编辑页URL中的docKey参数（备选）
    match = re.search(r'docKey=([^&]+)', url)
    if match:
        return match.group(1)
    
    # 如果URL本身就是node ID（没有协议前缀）
    if not url.startswith('http') and '/' not in url and '?' not in url:
        return url
    
    raise McpError(ErrorData(
        code=INVALID_PARAMS,
        message=f"无法从URL中提取workbookId: {url}"
    ))


def numberToColumnName(colNum: int) -> str:
    """
    将列数转换为Excel列名（1->A, 26->Z, 27->AA, 702->ZZ）
    
    Args:
        colNum: 列数
    
    Returns:
        Excel列名
    """
    if colNum <= 0:
        return 'A'
    result = ''
    while colNum > 0:
        colNum -= 1
        result = chr(65 + (colNum % 26)) + result
        colNum //= 26
    return result


async def getTokenAndOperatorId(aegisKey: str, aegisSecret: str, workid: str) -> tuple[str, str]:
    """
    从内部API获取钉钉访问令牌和操作者ID
    
    Args:
        aegisKey: Aegis密钥
        aegisSecret: Aegis密钥Secret
        workid: 工作ID
        
    Returns:
        (访问令牌, 操作者ID) 元组
        
    Raises:
        McpError: 当获取token失败时
    """
    # 尝试从缓存中读取token（基于workid缓存）
    cache_key = f"{workid}_{aegisKey}"
    current_time = time.time()
    
    # 检查缓存文件是否存在
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                cached_entry = cache_data.get(cache_key, {})
                cached_token = cached_entry.get('access_token')
                cached_operator_id = cached_entry.get('operator_id')
                expires_at = cached_entry.get('expires_at', 0)
                
                # 检查token是否仍然有效（提前5分钟过期，确保安全）
                if cached_token and cached_operator_id and expires_at > (current_time + 300):
                    return cached_token, cached_operator_id
        except Exception as e:
            logger.warning(f"读取缓存文件失败: {e}")
    
    # 缓存无效或不存在，重新请求
    url = f'{TOKEN_API_URL}?aegisKey={aegisKey}&aegisSecret={aegisSecret}&workid={workid}'
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(url, headers=COMMON_HEADERS)
            response.raise_for_status()
            rtnData = response.json()
            
            if rtnData and rtnData.get('ec') == 200:
                data = rtnData.get('data', {})
                accessToken = data.get('token')
                operatorId = data.get('operatorId')
                
                if not accessToken or not operatorId:
                    error_msg = f"API返回数据不完整\n【请求URL】{url}\n【完整响应】{json.dumps(rtnData, ensure_ascii=False, indent=2)}"
                    raise McpError(ErrorData(
                        code=INTERNAL_ERROR,
                        message=error_msg
                    ))
                
                # 保存到缓存文件（默认2小时有效期）
                try:
                    if os.path.exists(CACHE_FILE):
                        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                    else:
                        cache_data = {}
                    
                    cache_data[cache_key] = {
                        'access_token': accessToken,
                        'operator_id': operatorId,
                        'expires_at': current_time + 7200,  # 默认7200秒
                        'cached_at': current_time
                    }
                    
                    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, indent=2)
                except Exception as e:
                    logger.warning(f"保存缓存文件失败: {e}")
                
                return accessToken, operatorId
            else:
                error_msg = f"获取token失败\n【请求URL】{url}\n【错误码】{rtnData.get('ec', '未知')}\n【错误消息】{rtnData.get('em', '未知错误')}\n【完整响应】{json.dumps(rtnData, ensure_ascii=False, indent=2)}"
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=error_msg
                ))
        except httpx.HTTPError as e:
            error_msg = format_http_error(e, url, "获取钉钉访问令牌")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取token请求失败:\n{error_msg}"
            ))


async def getSheetList(
    workbookId: str,
    operatorId: str,
    accessToken: str
) -> List[Dict[str, Any]]:
    """
    获取工作簿中所有Sheet的列表
    
    Args:
        workbookId: 工作簿ID
        operatorId: 操作者ID
        accessToken: 访问令牌
        
    Returns:
        Sheet列表，每个元素包含id和name
        
    Raises:
        McpError: 当请求失败时
    """
    url = f'{API_BASE_URL}/workbooks/{workbookId}/sheets?operatorId={operatorId}'
    headers = {
        **COMMON_HEADERS,
        'x-acs-dingtalk-access-token': accessToken
    }
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            rtnJson = response.json()
            
            if "value" in rtnJson and isinstance(rtnJson["value"], list):
                sheets = []
                for item in rtnJson["value"]:
                    if isinstance(item, dict) and item.get("id"):
                        sheets.append({
                            "id": item.get("id"),
                            "name": item.get("name", "")
                        })
                return sheets
            else:
                response_text = ""
                try:
                    response_text = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
                except:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"API响应格式错误：缺少value字段\n【请求URL】{url}\n【响应内容】{response_text}"
                ))
        except httpx.HTTPStatusError as e:
            # token 失效时直接抛出，便于上层清除缓存并重试
            if is_invalid_auth_error(e):
                raise
            error_msg = format_http_error(e, url, "获取Sheet列表")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取Sheet列表失败:\n{error_msg}"
            ))
        except httpx.HTTPError as e:
            error_msg = format_http_error(e, url, "获取Sheet列表")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取Sheet列表失败:\n{error_msg}"
            ))


async def getSheetidByName(
    sheetname: Optional[str],
    workbookId: str,
    operatorId: str,
    accessToken: str
) -> tuple[str, str]:
    """
    根据Sheet名称获取Sheet ID和名称，如果未提供名称则返回第一个Sheet
    
    Args:
        sheetname: Sheet名称（可选，None则返回第一个Sheet）
        workbookId: 工作簿ID
        operatorId: 操作者ID
        accessToken: 访问令牌
        
    Returns:
        (Sheet ID, Sheet名称) 元组
        
    Raises:
        McpError: 当请求失败时
    """
    sheets = await getSheetList(workbookId, operatorId, accessToken)
    
    if not sheets:
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message="工作簿中没有找到任何Sheet"
        ))
    
    # 如果没有提供sheetname，返回第一个Sheet
    if not sheetname:
        first_sheet = sheets[0]
        return first_sheet["id"], first_sheet["name"]
    
    # 根据名称查找
    for sheet in sheets:
        if sheet.get("name") == sheetname:
            return sheet["id"], sheet["name"]
    
    # 如果未找到，抛出错误
    raise McpError(ErrorData(
        code=INVALID_PARAMS,
        message=f"未找到名为 '{sheetname}' 的Sheet。可用Sheet列表: {[s['name'] for s in sheets]}"
    ))


async def writeSheetData(
    url: str,
    data: List[List[Any]],
    aegisKey: Optional[str] = None,
    aegisSecret: Optional[str] = None,
    workid: Optional[str] = None,
    sheetname: Optional[str] = None,
    startRow: int = 1,
    startColumn: int = 1
) -> tuple[str, int, int]:
    """
    写入Excel表格数据
    
    Args:
        url: 钉钉Excel的完整URL
        data: 要写入的数据（二维数组）
        aegisKey: Aegis密钥（可选，未提供则使用环境变量）
        aegisSecret: Aegis密钥Secret（可选，未提供则使用环境变量）
        workid: 工作ID（可选，未提供则使用环境变量）
        sheetname: Sheet名称（可选，未提供则使用第一个Sheet）
        startRow: 起始行号（从1开始）
        startColumn: 起始列号（从1开始）
        
    Returns:
        (Sheet名称, 写入的行数, 写入的列数) 元组
        
    Raises:
        McpError: 当写入数据失败时
    """
    # 从URL中提取workbookId
    workbookId = extract_workbook_id_from_url(url)
    
    # 获取参数（优先使用传入的参数，其次环境变量）
    final_aegisKey = aegisKey or DEFAULT_AEGIS_KEY
    final_aegisSecret = aegisSecret or DEFAULT_AEGIS_SECRET
    final_workid = workid or DEFAULT_WORKID
    
    if not data:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="数据不能为空"
        ))
    
    # 计算数据范围
    num_rows = len(data)
    num_cols = max(len(row) for row in data) if data else 0
    
    if num_cols == 0:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="数据至少需要一列"
        ))
    
    # 准备写入数据（与 token 无关，可提前计算）
    normalized_data = []
    for row in data:
        normalized_row = []
        for cell in row:
            if cell is None:
                normalized_row.append('')
            else:
                normalized_row.append(str(cell))
        normalized_row = normalized_row + [''] * (num_cols - len(normalized_row))
        normalized_data.append(normalized_row[:num_cols])
    request_body = {"values": normalized_data}
    
    # 支持 token 失效时自动清除缓存并重试一次
    for attempt in range(2):
        try:
            accessToken, operatorId = await getTokenAndOperatorId(final_aegisKey, final_aegisSecret, final_workid)
            sheetid, actual_sheetname = await getSheetidByName(sheetname, workbookId, operatorId, accessToken)
            
            endRow = startRow + num_rows - 1
            startColName = numberToColumnName(startColumn)
            endColName = numberToColumnName(startColumn + num_cols - 1)
            range_str = f'{startColName}{startRow}:{endColName}{endRow}'
            write_url = f'{API_BASE_URL}/workbooks/{workbookId}/sheets/{sheetid}/ranges/{range_str}?operatorId={operatorId}'
            headers = {
                **COMMON_HEADERS,
                'x-acs-dingtalk-access-token': accessToken
            }
            
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.put(write_url, headers=headers, json=request_body)
                response.raise_for_status()
            
            if response.status_code in [200, 204]:
                return actual_sheetname, num_rows, num_cols
            else:
                response_text = ""
                try:
                    response_text = response.text[:1000] if hasattr(response, 'text') else str(response.content[:1000])
                    if len(response_text) > 1000:
                        response_text = response_text[:1000] + "... (内容已截断)"
                except Exception:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"写入数据失败\n【HTTP状态码】{response.status_code}\n【请求URL】{write_url}\n【响应内容】{response_text}"
                ))
        except httpx.HTTPStatusError as e:
            if attempt == 0 and is_invalid_auth_error(e):
                clear_token_cache(final_aegisKey, final_aegisSecret, final_workid)
                continue
            req_url = getattr(e.request, 'url', '') if e.request else ''
            error_msg = format_http_error(e, str(req_url), "写入Sheet数据")
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"写入Sheet数据失败:\n{error_msg}"))
        except httpx.HTTPError as e:
            req_url = getattr(e.request, 'url', '') if hasattr(e, 'request') and e.request else ''
            error_msg = format_http_error(e, str(req_url), "写入Sheet数据")
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"写入Sheet数据失败:\n{error_msg}"))


async def getSheetData(
    url: str,
    aegisKey: Optional[str] = None,
    aegisSecret: Optional[str] = None,
    workid: Optional[str] = None,
    sheetname: Optional[str] = None
) -> tuple[List[List[Any]], str]:
    """
    获取Excel表格的所有数据（简化版，用于删除和添加操作）
    
    Args:
        url: 钉钉Excel的完整URL
        aegisKey: Aegis密钥（可选，未提供则使用环境变量）
        aegisSecret: Aegis密钥Secret（可选，未提供则使用环境变量）
        workid: 工作ID（可选，未提供则使用环境变量）
        sheetname: Sheet名称（可选，未提供则使用第一个Sheet）
        
    Returns:
        (表格数据列表（二维数组），Sheet名称) 元组
    """
    # 从URL中提取workbookId
    workbookId = extract_workbook_id_from_url(url)
    
    # 获取参数（优先使用传入的参数，其次环境变量）
    final_aegisKey = aegisKey or DEFAULT_AEGIS_KEY
    final_aegisSecret = aegisSecret or DEFAULT_AEGIS_SECRET
    final_workid = workid or DEFAULT_WORKID
    
    # 支持 token 失效时自动清除缓存并重试一次
    for attempt in range(2):
        try:
            accessToken, operatorId = await getTokenAndOperatorId(final_aegisKey, final_aegisSecret, final_workid)
            sheetid, actual_sheetname = await getSheetidByName(sheetname, workbookId, operatorId, accessToken)
            break
        except httpx.HTTPStatusError as e:
            if attempt == 0 and is_invalid_auth_error(e):
                clear_token_cache(final_aegisKey, final_aegisSecret, final_workid)
                continue
            raise
    
    headers = {
        **COMMON_HEADERS,
        'x-acs-dingtalk-access-token': accessToken
    }
    
    # 获取sheet维度信息
    url_sheet_info = f'{API_BASE_URL}/workbooks/{workbookId}/sheets/{sheetid}?select=values&operatorId={operatorId}'
    
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(url_sheet_info, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            error_msg = format_http_error(e, url_sheet_info, "获取Sheet维度信息")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取Sheet维度信息失败:\n{error_msg}"
            ))
        
        maxRow = 10000
        maxColumn = 'ZZ'
        
        if response.status_code == 200:
            try:
                sheetJson = response.json()
                if 'rowCount' in sheetJson and sheetJson['rowCount']:
                    maxRow = sheetJson['rowCount']
                if 'columnCount' in sheetJson and sheetJson['columnCount']:
                    columnCount = sheetJson['columnCount']
                    maxColumn = numberToColumnName(columnCount)
            except Exception as e:
                logger.warning(f"解析Sheet维度信息失败，使用默认范围: {e}")
        
        # 获取数据
        range_str = f'A1:{maxColumn}{maxRow}'
        data_url = f'{API_BASE_URL}/workbooks/{workbookId}/sheets/{sheetid}/ranges/{range_str}?select=values&operatorId={operatorId}'
        
        try:
            response = await client.get(data_url, headers=headers)
            response.raise_for_status()
            
            if response.status_code == 200:
                rtnJson = response.json()
                values = rtnJson.get('values', [])
                return values if values else [], actual_sheetname
            else:
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"获取数据失败，HTTP状态码: {response.status_code}"
                ))
        except httpx.HTTPError as e:
            error_msg = format_http_error(e, data_url, f"获取Sheet数据范围 {range_str}")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取Sheet数据失败:\n{error_msg}"
            ))


async def deleteRowBySeq(
    url: str,
    seqNumber: int,
    aegisKey: Optional[str] = None,
    aegisSecret: Optional[str] = None,
    workid: Optional[str] = None,
    sheetname: Optional[str] = None
) -> tuple[str, int]:
    """
    删除指定序号的行，并重新调整序号
    
    Args:
        url: 钉钉Excel的完整URL
        seqNumber: 要删除的序号（第一列的序号值）
        aegisKey: Aegis密钥（可选，未提供则使用环境变量）
        aegisSecret: Aegis密钥Secret（可选，未提供则使用环境变量）
        workid: 工作ID（可选，未提供则使用环境变量）
        sheetname: Sheet名称（可选，未提供则使用第一个Sheet）
        
    Returns:
        (Sheet名称, 删除的行数) 元组
    """
    # 读取所有数据
    all_data, actual_sheetname = await getSheetData(url, aegisKey, aegisSecret, workid, sheetname)
    
    if not all_data:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="表格中没有数据"
        ))
    
    # 表头
    header = all_data[0] if all_data else []
    
    # 数据行（排除表头）
    data_rows = all_data[1:] if len(all_data) > 1 else []
    
    # 查找并删除指定序号的行
    deleted = False
    filtered_rows = []
    new_seq = 1
    
    for row in data_rows:
        # 获取序号（第一列）
        seq = row[0] if row else None
        
        # 尝试转换为数字进行比较
        try:
            seq_int = int(seq) if seq is not None else None
            if seq_int == seqNumber:
                deleted = True
                continue  # 跳过这一行
        except (ValueError, TypeError):
            # 如果序号不是数字，直接比较
            if seq == seqNumber:
                deleted = True
                continue
        
        # 重新设置序号
        if seq is not None:
            new_row = [new_seq] + list(row[1:])
            filtered_rows.append(new_row)
            new_seq += 1
        else:
            filtered_rows.append(row)
    
    if not deleted:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message=f"未找到序号为 {seqNumber} 的行"
        ))
    
    # 准备写入的数据（包含表头）
    data_to_write = [header] + filtered_rows
    
    # 重新写入整个表格
    await writeSheetData(
        url=url,
        data=data_to_write,
        aegisKey=aegisKey,
        aegisSecret=aegisSecret,
        workid=workid,
        sheetname=sheetname,
        startRow=1,
        startColumn=1
    )
    
    return actual_sheetname, 1


async def addRow(
    url: str,
    rowData: List[Any],
    aegisKey: Optional[str] = None,
    aegisSecret: Optional[str] = None,
    workid: Optional[str] = None,
    sheetname: Optional[str] = None
) -> tuple[str, int]:
    """
    在表格末尾添加新行
    
    Args:
        url: 钉钉Excel的完整URL
        rowData: 要添加的行数据（一维数组）
        aegisKey: Aegis密钥（可选，未提供则使用环境变量）
        aegisSecret: Aegis密钥Secret（可选，未提供则使用环境变量）
        workid: 工作ID（可选，未提供则使用环境变量）
        sheetname: Sheet名称（可选，未提供则使用第一个Sheet）
        
    Returns:
        (Sheet名称, 添加的行号) 元组
    """
    # 读取所有数据
    all_data, actual_sheetname = await getSheetData(url, aegisKey, aegisSecret, workid, sheetname)
    
    if not all_data:
        raise McpError(ErrorData(
            code=INVALID_PARAMS,
            message="表格中没有数据，无法确定添加位置"
        ))
    
    # 计算新行的位置（表头1行 + 数据行数 + 1）
    new_row_number = len(all_data) + 1
    
    # 写入新行
    await writeSheetData(
        url=url,
        data=[rowData],
        aegisKey=aegisKey,
        aegisSecret=aegisSecret,
        workid=workid,
        sheetname=sheetname,
        startRow=new_row_number,
        startColumn=1
    )
    
    return actual_sheetname, new_row_number


# ==================== MCP服务器 ====================
async def serve() -> None:
    """运行钉钉Excel写入MCP服务器"""
    server = Server("mcp-dingtalk-excel-write")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="write_sheet_data",
                description="向钉钉Excel表格中指定Sheet写入数据",
                inputSchema=WriteSheetDataRequest.model_json_schema(),
            ),
            Tool(
                name="delete_row_by_seq",
                description="删除钉钉Excel表格中指定序号的行，并自动重新调整序号",
                inputSchema=DeleteRowRequest.model_json_schema(),
            ),
            Tool(
                name="add_row",
                description="在钉钉Excel表格末尾添加新行",
                inputSchema=AddRowRequest.model_json_schema(),
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "write_sheet_data":
            try:
                args = WriteSheetDataRequest(**arguments)
            except ValueError as e:
                raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))
            
            try:
                sheetname, num_rows, num_cols = await writeSheetData(
                    args.url,
                    args.data,
                    args.aegisKey,
                    args.aegisSecret,
                    args.workid,
                    args.sheetname,
                    args.startRow,
                    args.startColumn
                )
                
                output = [f"✅ 成功写入Excel表格数据"]
                output.append(f"\n📊 Sheet名称: {sheetname}")
                if args.sheetname:
                    output.append(f"   (请求的Sheet: {args.sheetname})")
                else:
                    output.append(f"   (使用默认的第一个Sheet)")
                output.append(f"🔗 Excel URL: {args.url}")
                output.append(f"📍 写入位置: 行{args.startRow}列{args.startColumn} 到 行{args.startRow + num_rows - 1}列{args.startColumn + num_cols - 1}")
                output.append(f"📏 写入数据: {num_rows}行 × {num_cols}列")
                
                return [TextContent(type="text", text="\n".join(output))]
                
            except McpError:
                raise
            except Exception as e:
                error_msg = format_exception(e, "写入Excel表格数据")
                # 添加请求参数信息
                try:
                    error_msg += f"\n【请求参数】\n"
                    error_msg += f"  - URL: {args.url}\n"
                    error_msg += f"  - Sheet名称: {args.sheetname or '(使用默认第一个Sheet)'}\n"
                    error_msg += f"  - 起始位置: 行{args.startRow}列{args.startColumn}\n"
                    error_msg += f"  - 数据行数: {len(args.data)}\n"
                    error_msg += f"  - AegisKey: {'已提供' if args.aegisKey else '使用环境变量'}\n"
                    error_msg += f"  - WorkID: {args.workid or '使用环境变量'}\n"
                except:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"写入Excel数据失败:\n{error_msg}"
                ))
        elif name == "delete_row_by_seq":
            try:
                args = DeleteRowRequest(**arguments)
            except ValueError as e:
                raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))
            
            try:
                sheetname, deleted_count = await deleteRowBySeq(
                    args.url,
                    args.seqNumber,
                    args.aegisKey,
                    args.aegisSecret,
                    args.workid,
                    args.sheetname
                )
                
                output = [f"✅ 成功删除序号为 {args.seqNumber} 的行"]
                output.append(f"\n📊 Sheet名称: {sheetname}")
                if args.sheetname:
                    output.append(f"   (请求的Sheet: {args.sheetname})")
                else:
                    output.append(f"   (使用默认的第一个Sheet)")
                output.append(f"🔗 Excel URL: {args.url}")
                output.append(f"🗑️ 删除行数: {deleted_count}")
                output.append(f"📝 说明: 序号已自动重新调整")
                
                return [TextContent(type="text", text="\n".join(output))]
                
            except McpError:
                raise
            except Exception as e:
                error_msg = format_exception(e, "删除Excel行")
                try:
                    error_msg += f"\n【请求参数】\n"
                    error_msg += f"  - URL: {args.url}\n"
                    error_msg += f"  - 序号: {args.seqNumber}\n"
                    error_msg += f"  - Sheet名称: {args.sheetname or '(使用默认第一个Sheet)'}\n"
                except:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"删除Excel行失败:\n{error_msg}"
                ))
        elif name == "add_row":
            try:
                args = AddRowRequest(**arguments)
            except ValueError as e:
                raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))
            
            try:
                sheetname, row_number = await addRow(
                    args.url,
                    args.rowData,
                    args.aegisKey,
                    args.aegisSecret,
                    args.workid,
                    args.sheetname
                )
                
                output = [f"✅ 成功添加新行"]
                output.append(f"\n📊 Sheet名称: {sheetname}")
                if args.sheetname:
                    output.append(f"   (请求的Sheet: {args.sheetname})")
                else:
                    output.append(f"   (使用默认的第一个Sheet)")
                output.append(f"🔗 Excel URL: {args.url}")
                output.append(f"📍 添加位置: 第{row_number}行")
                output.append(f"📝 行数据: {args.rowData}")
                
                return [TextContent(type="text", text="\n".join(output))]
                
            except McpError:
                raise
            except Exception as e:
                error_msg = format_exception(e, "添加Excel行")
                try:
                    error_msg += f"\n【请求参数】\n"
                    error_msg += f"  - URL: {args.url}\n"
                    error_msg += f"  - 行数据: {args.rowData}\n"
                    error_msg += f"  - Sheet名称: {args.sheetname or '(使用默认第一个Sheet)'}\n"
                except:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"添加Excel行失败:\n{error_msg}"
                ))
        else:
            raise McpError(ErrorData(
                code=INVALID_PARAMS,
                message=f"未知工具: {name}"
            ))
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


def main():
    """主入口函数"""
    asyncio.run(serve())


if __name__ == "__main__":
    main()

