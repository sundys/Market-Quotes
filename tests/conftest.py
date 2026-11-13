"""pytest 公共夹具。

Windows + Python 3.12 上 `Path.mkdir(mode=0o700)`（pytest 创建 tmp_path 时内部用法）
会生成“仅 Administrators/SYSTEM 可访问”的 ACL，导致受限账户下临时目录不可写。
这里改用默认权限创建，保证测试在受限 Windows 环境也能跑。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    base = Path(tempfile.gettempdir()) / f"mq-test-{uuid.uuid4().hex}"
    os.mkdir(base)  # 不带 mode，继承默认 ACL
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)
