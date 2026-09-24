#!/usr/bin/env python3
"""
检测当前环境是否满足本项目（pytest 数据驱动骨架）运行条件。
运行: python3 scripts/check_env.py
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))


def ok(msg):
    print(f"  \033[92m✓\033[0m {msg}")
    sys.stdout.flush()


def fail(msg):
    print(f"  \033[91m✗\033[0m {msg}")
    sys.stdout.flush()


def warn(msg):
    print(f"  \033[93m!\033[0m {msg}")
    sys.stdout.flush()


def section(title):
    print(f"\n\033[1m{title}\033[0m")
    sys.stdout.flush()


def check_python():
    section("1. Python 版本")
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v.major >= 3 and v.minor >= 9:
        ok(f"Python {ver} (满足 >= 3.9)")
        return True
    fail(f"Python {ver} (需要 >= 3.9)")
    return False


def check_project_path():
    section("2. 项目路径")
    if not os.path.isdir(PROJECT_ROOT):
        fail(f"项目根目录不存在: {PROJECT_ROOT}")
        return False
    ok(f"项目根目录: {PROJECT_ROOT}")
    data_dir = os.path.join(PROJECT_ROOT, "data")
    if os.path.isdir(data_dir):
        ok(f"data 目录存在: {data_dir}")
    else:
        warn(f"data 目录不存在: {data_dir}")
    business_case = os.path.join(PROJECT_ROOT, "business_case")
    if os.path.isdir(business_case):
        ok("business_case 目录存在")
    else:
        fail("business_case 目录不存在")
        return False
    return True


def check_conftest_project_root():
    section("3. conftest.py")
    conftest_path = os.path.join(PROJECT_ROOT, "conftest.py")
    if not os.path.isfile(conftest_path):
        warn("conftest.py 不存在")
        return True
    ok("conftest.py 存在（project_root 建议基于 __file__ 动态计算）")
    return True


def check_dependencies():
    section("4. Python 依赖")
    required = [
        ("pytest", "pytest"),
        ("PyMySQL", "pymysql"),
        ("redis", "redis"),
        ("multipledispatch", "multipledispatch"),
    ]
    missing = []
    for display_name, import_name in required:
        try:
            __import__(import_name)
            ok(display_name)
        except ImportError:
            fail(display_name)
            missing.append(display_name)
    if missing:
        print("  安装: pip install -r requirements.txt")
        return False
    return True


def check_env_file():
    section("5. 可选配置")
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.isfile(env_path):
        ok(".env 已存在")
    else:
        warn(".env 不存在时可复制 .env.example")
    return True


def main():
    print("yaahlan-calc-salary-test 环境检测")
    print("=" * 50)
    results = []
    results.append(("Python", check_python()))
    results.append(("项目路径", check_project_path()))
    results.append(("conftest", check_conftest_project_root()))
    results.append(("依赖", check_dependencies()))
    check_env_file()

    section("汇总")
    required_ok = all(r[1] for r in results)
    if required_ok:
        print("  环境基本满足，可在项目根执行: pytest")
    else:
        print("  存在必须项未满足，请按上述提示修复。")
    print()
    return 0 if required_ok else 1


if __name__ == "__main__":
    sys.exit(main())
