import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)


class JsonUtils:
    @staticmethod
    def jsonfile_to_dict(category: str, json_name: str) -> Optional[Dict[str, Any]]:
        file_util = FileUtils()
        file_path = file_util.get_file_path(category, json_name)
        if file_path is None:
            return None
        if not Path(file_path).exists():
            logger.error("case配置文件不存在：%s", file_path)
            return None
        try:
            logger.debug("file_path: %s", file_path)
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if data is None:
                logger.error("读取json文件失败，文件内容为空：%s", file_path)
                return None
            logger.debug("file_data keys: %s", list(data) if isinstance(data, dict) else type(data))
            return data
        except (OSError, UnicodeError) as e:
            logger.error("读取json文件发生IO错误：%s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("读取json文件JSON解析失败：%s", e)
            return None
