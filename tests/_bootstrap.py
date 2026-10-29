"""测试引导：让任意检出目录名都能以 ``astrbot_plugin_multisim`` 导入。

仓库根目录就是插件包本身；GitHub 仓库名为 ``astrbot-multisim-connect``，克隆后的
目录名不是合法的 Python 标识符，直接 ``import astrbot_plugin_multisim`` 会失败。
这里把检出根目录注册成规范包名，测试与冒烟脚本便可以始终使用绝对导入。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

PACKAGE_NAME = "astrbot_plugin_multisim"
ROOT = Path(__file__).resolve().parents[1]


def ensure_package_importable() -> None:
    """在 ``sys.modules`` 中提供 ``astrbot_plugin_multisim``（幂等）。"""
    if PACKAGE_NAME in sys.modules:
        return

    parent = str(ROOT.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    if ROOT.name == PACKAGE_NAME:
        importlib.import_module(PACKAGE_NAME)
        return

    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - 结构损坏时才会发生
        raise RuntimeError(f"无法从 {ROOT} 加载 {PACKAGE_NAME}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
