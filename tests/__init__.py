"""插件测试包。

导入本包时会自动调用 :func:`tests._bootstrap.ensure_package_importable`，
因此测试模块可以直接 ``from astrbot_plugin_multisim... import ...``。

运行方式（仓库根目录）::

    python -m unittest discover -s tests -t .
"""

from ._bootstrap import ensure_package_importable

ensure_package_importable()
