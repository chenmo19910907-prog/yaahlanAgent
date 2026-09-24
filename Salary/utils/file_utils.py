import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileUtils:
    """从项目根下定位 data/<category>/ 文件（与 soulchill-api-test 架构一致）。"""

    def _resolve_data_dir(self, category: str) -> Optional[Path]:
        current_path = Path(__file__).resolve().parent
        for parent in current_path.parents:
            potential_dir = parent / "data" / category
            if potential_dir.is_dir():
                return potential_dir
        logger.error("Data directory not found for category=%s", category)
        return None

    def get_file_path(self, category: str, file_name: str) -> Optional[Path]:
        data_dir = self._resolve_data_dir(category)
        if not data_dir:
            return None
        path = data_dir / file_name
        logger.debug("Resolved data file: %s", path)
        return path

    def get_file_dir(self, category: str) -> Optional[Path]:
        return self._resolve_data_dir(category)
