"""MOA 目录路径常量。"""

from __future__ import annotations

import os


def moa_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_dir() -> str:
    return os.path.join(moa_dir(), "config")


def thresholds_path() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return str(module_path("moaThresholds", "MOA/config/thresholds.json"))
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return os.path.join(config_dir(), "thresholds.json")


def registry_path() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return str(module_path("moaRegistry", "MOA/config/registry.json"))
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return os.path.join(config_dir(), "registry.json")


def runtime_yaml_path() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return str(module_path("moaRuntimeYaml", "MOA/config/moa.yaml"))
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return os.path.join(config_dir(), "moa.yaml")


def templates_dir() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return str(module_path("moaTemplates", "MOA/templates"))
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return os.path.join(moa_dir(), "templates")


def usage_doc_path() -> str:
    return os.path.join(moa_dir(), "使用方法.md")
