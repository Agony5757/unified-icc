"""E2E test configuration.

By default these tests use the same isolated config location as unit tests.
Set RUN_FEISHU_E2E=1 to opt into real ~/.unified-icc/config.yaml checks.
"""
import os

if os.getenv("RUN_FEISHU_E2E") == "1":
    # Ensure manually requested Feishu E2E tests use the real config location.
    os.environ.pop("UNIFIED_ICC_DIR", None)
    os.environ.pop("TMUX_SESSION_NAME", None)
