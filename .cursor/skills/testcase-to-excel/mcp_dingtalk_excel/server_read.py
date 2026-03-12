#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钉钉Excel解析 MCP 服务器
提供钉钉Excel表格数据获取功能
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
# 钉钉API单次请求最大单元格数限制
MAX_CELLS_PER_REQUEST = 30000

# 从环境变量获取默认值
DEFAULT_AEGIS_KEY = os.getenv("DINGTALK_AEGIS_KEY", "8e052add-cbef-41aa-aac3-9c16ed1cf4b7")
DEFAULT_AEGIS_SECRET = os.getenv("DINGTALK_AEGIS_SECRET", "17764e8a-655f-4335-927e-4e1205bc49e0")
DEFAULT_WORKID = os.getenv("DINGTALK_WORKID", "110010")

# 从环境变量获取默认输出目录（如果将来需要保存文件，展开~符号）
_default_output_dir = os.getenv("DINGTALK_EXCEL_OUTPUT_DIR", os.path.expanduser("~/Documents/cursor-mcp/dingExcel"))
DEFAULT_OUTPUT_DIR = os.path.expanduser(_default_output_dir)

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
    
    # 如果是RequestError，获取更多信息
    elif isinstance(e, httpx.RequestError):
        if hasattr(e, 'request') and e.request:
            error_parts.append(f"【请求方法】{e.request.method}")
            if hasattr(e.request, 'url') and e.request.url:
                error_parts.append(f"【请求URL】{e.request.url}")
            elif url:
                error_parts.append(f"【请求URL】{url}")
    
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
class GetSheetInfoRequest(BaseModel):
    """获取Excel表格数据请求参数"""
    url: Annotated[
        str,
        Field(description="钉钉Excel的完整URL，例如：https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r")
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
    """清除指定 key 的 token 缓存"""
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
                # 输出完整的响应内容以便调试
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
            if is_invalid_auth_error(e):
                raise
            # 尝试获取详细的响应内容
            error_details = []
            error_details.append(f"【请求URL】{url}")
            error_details.append(f"【请求方法】GET")
            error_details.append(f"【错误类型】{type(e).__name__}")
            error_details.append(f"【错误消息】{str(e)}")
            
            # 如果是HTTPStatusError，获取响应详情
            if isinstance(e, httpx.HTTPStatusError):
                response = e.response
                error_details.append(f"【HTTP状态码】{response.status_code}")
                error_details.append(f"【状态文本】{response.reason_phrase}")
                
                # 尝试解析响应JSON
                try:
                    response_json = response.json()
                    error_details.append(f"【响应JSON】")
                    error_details.append(json.dumps(response_json, indent=2, ensure_ascii=False))
                    
                    # 提取关键错误信息
                    if 'code' in response_json:
                        error_details.append(f"\n【错误代码】{response_json['code']}")
                    if 'message' in response_json:
                        error_details.append(f"【错误消息】{response_json['message']}")
                    if 'requestid' in response_json:
                        error_details.append(f"【请求ID】{response_json['requestid']}")
                except:
                    # 如果不是JSON，尝试获取文本内容
                    try:
                        response_text = response.text
                        if len(response_text) > 1000:
                            response_text = response_text[:1000] + "... (内容已截断)"
                        error_details.append(f"【响应文本】{response_text}")
                    except:
                        pass
            
            error_msg = "\n".join(error_details)
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


async def getRangeData(
    client: httpx.AsyncClient,
    workbookId: str,
    sheetid: str,
    operatorId: str,
    accessToken: str,
    startRow: int,
    endRow: int,
    maxColumn: str
) -> List[List[Any]]:
    """
    获取指定范围的数据
    
    Args:
        client: HTTP客户端
        workbookId: 工作簿ID
        sheetid: Sheet ID
        operatorId: 操作者ID
        accessToken: 访问令牌
        startRow: 起始行号（从1开始）
        endRow: 结束行号（包含）
        maxColumn: 最大列名（如'AO'）
        
    Returns:
        指定范围的数据列表（二维数组）
        
    Raises:
        McpError: 当请求失败时
    """
    headers = {
        **COMMON_HEADERS,
        'x-acs-dingtalk-access-token': accessToken
    }
    
    # 构建范围字符串，如 A1:AO100
    range_str = f'A{startRow}:{maxColumn}{endRow}'
    data_url = f'{API_BASE_URL}/workbooks/{workbookId}/sheets/{sheetid}/ranges/{range_str}?select=values&operatorId={operatorId}'
    
    try:
        response = await client.get(data_url, headers=headers)
        response.raise_for_status()
        
        if response.status_code == 200:
            rtnJson = response.json()
            values = rtnJson.get('values', [])
            return values if values else []
        else:
            response_text = ""
            try:
                response_text = response.text[:1000] if hasattr(response, 'text') else str(response.content[:1000])
                if len(response_text) > 1000:
                    response_text = response_text[:1000] + "... (内容已截断)"
            except:
                pass
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"请求失败\n【HTTP状态码】{response.status_code}\n【请求URL】{data_url}\n【响应内容】{response_text}"
            ))
    except httpx.HTTPError as e:
        error_msg = format_http_error(e, data_url, f"获取Sheet数据范围 {range_str}")
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message=f"获取Sheet数据失败:\n{error_msg}"
        ))


async def getSheetInfo(
    url: str,
    aegisKey: Optional[str] = None,
    aegisSecret: Optional[str] = None,
    workid: Optional[str] = None,
    sheetname: Optional[str] = None
) -> tuple[List[List[Any]], str]:
    """
    获取Excel表格的所有数据
    
    Args:
        url: 钉钉Excel的完整URL
        aegisKey: Aegis密钥（可选，未提供则使用环境变量）
        aegisSecret: Aegis密钥Secret（可选，未提供则使用环境变量）
        workid: 工作ID（可选，未提供则使用环境变量）
        sheetname: Sheet名称（可选，未提供则使用第一个Sheet）
        
    Returns:
        (表格数据列表（二维数组），已过滤空行, Sheet名称) 元组
        
    Raises:
        McpError: 当获取数据失败时
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
    
    # 使用同一个client处理所有请求
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # 先获取sheet的维度信息，以确定数据范围
        url_sheet_info = f'{API_BASE_URL}/workbooks/{workbookId}/sheets/{sheetid}?select=values&operatorId={operatorId}'
        
        try:
            response = await client.get(url_sheet_info, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            error_msg = format_http_error(e, url_sheet_info, "获取Sheet维度信息")
            raise McpError(ErrorData(
                code=INTERNAL_ERROR,
                message=f"获取Sheet维度信息失败:\n{error_msg}"
            ))
        
        # 获取sheet维度信息
        maxRow = 10000  # 默认最大行数（足够大的值以包含所有数据）
        maxColumn = 'ZZ'  # 默认最大列数（702列，足够大）
        columnCount = 702  # 默认列数
        
        if response.status_code == 200:
            try:
                sheetJson = response.json()
                # 如果API返回了维度信息，使用实际维度；否则使用默认值
                if 'rowCount' in sheetJson and sheetJson['rowCount']:
                    maxRow = sheetJson['rowCount']
                if 'columnCount' in sheetJson and sheetJson['columnCount']:
                    # 将列数转换为Excel列名（如26->Z, 27->AA）
                    columnCount = sheetJson['columnCount']
                    maxColumn = numberToColumnName(columnCount)
            except Exception as e:
                logger.warning(f"解析Sheet维度信息失败，使用默认范围: {e}")
        
        # 计算总单元格数
        totalCells = maxRow * columnCount
        
        # 如果总单元格数超过限制，需要分批获取
        if totalCells > MAX_CELLS_PER_REQUEST:
            # 计算每批最多可以获取多少行（留一些余量，避免边界情况）
            rowsPerBatch = MAX_CELLS_PER_REQUEST // columnCount - 1
            if rowsPerBatch < 1:
                rowsPerBatch = 1
            
            logger.info(f"数据量过大（{totalCells}个单元格），将分批获取。每批约{rowsPerBatch}行，共需{(maxRow + rowsPerBatch - 1) // rowsPerBatch}批")
            
            # 分批获取数据
            all_values = []
            batch_num = 0
            for startRow in range(1, maxRow + 1, rowsPerBatch):
                endRow = min(startRow + rowsPerBatch - 1, maxRow)
                batch_num += 1
                
                logger.info(f"正在获取第 {batch_num} 批数据: 行 {startRow} 到 {endRow}")
                
                try:
                    batch_values = await getRangeData(
                        client, workbookId, sheetid, operatorId, accessToken,
                        startRow, endRow, maxColumn
                    )
                    all_values.extend(batch_values)
                except Exception as e:
                    error_msg = format_exception(e, f"获取第 {batch_num} 批数据（行 {startRow}-{endRow}）")
                    raise McpError(ErrorData(
                        code=INTERNAL_ERROR,
                        message=f"分批获取数据失败:\n{error_msg}"
                    ))
            
            values = all_values
        else:
            # 数据量不大，一次性获取
            try:
                values = await getRangeData(
                    client, workbookId, sheetid, operatorId, accessToken,
                    1, maxRow, maxColumn
                )
            except Exception as e:
                error_msg = format_exception(e, "获取Sheet数据")
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"获取Sheet数据失败:\n{error_msg}"
                ))
        
        if not values:
            return [], actual_sheetname
        
        # 过滤掉所有单元格都为空的行的处理逻辑
        filtered_values = []
        for row in values:
            # 检查这一行是否所有单元格都为空
            is_empty_row = True
            if isinstance(row, list):
                for cell in row:
                    # 如果单元格不是None、空字符串，且去除空白后不为空，则这一行不为空
                    if cell is not None and str(cell).strip():
                        is_empty_row = False
                        break
            else:
                # 如果row不是列表，检查它本身是否为空
                if row is not None and str(row).strip():
                    is_empty_row = False
            
            # 只有当行不为空时才添加到结果中
            if not is_empty_row:
                filtered_values.append(row)
        
        return filtered_values, actual_sheetname


# ==================== MCP服务器 ====================
async def serve() -> None:
    """运行钉钉Excel解析MCP服务器"""
    server = Server("mcp-dingtalk-excel")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="get_sheet_info",
                description="获取钉钉Excel表格中指定Sheet的所有数据（自动过滤空行）",
                inputSchema=GetSheetInfoRequest.model_json_schema(),
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "get_sheet_info":
            try:
                args = GetSheetInfoRequest(**arguments)
            except ValueError as e:
                raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))
            
            try:
                values, actual_sheetname = await getSheetInfo(
                    args.url,
                    args.aegisKey,
                    args.aegisSecret,
                    args.workid,
                    args.sheetname
                )
                
                output = [f"✅ 成功获取Excel表格数据"]
                output.append(f"\n📊 Sheet名称: {actual_sheetname}")
                if args.sheetname:
                    output.append(f"   (请求的Sheet: {args.sheetname})")
                else:
                    output.append(f"   (使用默认的第一个Sheet)")
                output.append(f"🔗 Excel URL: {args.url}")
                output.append(f"📏 数据行数: {len(values)}")
                
                if values:
                    # 显示前几行数据作为预览
                    preview_rows = min(3, len(values))
                    output.append(f"\n📄 数据预览（前{preview_rows}行）:")
                    for i, row in enumerate(values[:preview_rows], 1):
                        output.append(f"  行{i}: {row}")
                    
                    if len(values) > preview_rows:
                        output.append(f"  ... 还有 {len(values) - preview_rows} 行数据")
                
                # 将完整数据转换为JSON格式返回
                output.append(f"\n📦 完整数据（JSON格式）:")
                output.append(json.dumps(values, ensure_ascii=False, indent=2))
                
                return [TextContent(type="text", text="\n".join(output))]
                
            except McpError:
                raise
            except Exception as e:
                error_msg = format_exception(e, "获取Excel表格数据")
                # 添加请求参数信息
                try:
                    error_msg += f"\n【请求参数】\n"
                    error_msg += f"  - URL: {args.url}\n"
                    error_msg += f"  - Sheet名称: {args.sheetname or '(使用默认第一个Sheet)'}\n"
                    error_msg += f"  - AegisKey: {'已提供' if args.aegisKey else '使用环境变量'}\n"
                    error_msg += f"  - WorkID: {args.workid or '使用环境变量'}\n"
                except:
                    pass
                raise McpError(ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"获取Excel数据失败:\n{error_msg}"
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

