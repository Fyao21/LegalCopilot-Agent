"""无需 pytest 的统一自测入口。"""

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 自动测试必须完全可复现，不能读取开发者本机 Key 或产生真实模型费用。
os.environ["OFFLINE_MODE"] = "true"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["DATABASE_URL"] = f"sqlite:///{(PROJECT_ROOT / 'data' / 'test_legal_copilot.db').as_posix()}"
for secret_name in ("LLM_API_KEY", "OPENAI_API_KEY", "EMBEDDING_API_KEY"):
    os.environ.pop(secret_name, None)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
