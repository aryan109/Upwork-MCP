"""
Test configuration and isolation fixtures for Upwork MCP Engine.
Ensures tests never modify the real repository root files or user upwork_engine state.
"""
import os
import shutil
import tempfile
from pathlib import Path
import pytest

# Enforce test mode immediately before imports
os.environ["UPWORK_TEST_MODE"] = "1"

@pytest.fixture(autouse=True, scope="session")
def enforce_test_mode_env():
    """Ensure UPWORK_TEST_MODE is set for the whole test session."""
    os.environ["UPWORK_TEST_MODE"] = "1"
    yield
    os.environ.pop("UPWORK_TEST_MODE", None)

@pytest.fixture(autouse=True)
def isolated_test_engine_dir(tmp_path, monkeypatch):
    """
    Ensure every test operates in a sterile, temporary engine directory.
    Patches config paths and state manager locations.
    """
    test_engine_dir = tmp_path / "upwork_engine_test"
    test_engine_dir.mkdir(parents=True, exist_ok=True)
    state_dir = test_engine_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("UPWORK_ENGINE_DIR", str(test_engine_dir))
    monkeypatch.setenv("UPWORK_TEST_MODE", "1")

    # Patch config module attributes
    import aryan_implementation.engine.config as cfg
    monkeypatch.setattr(cfg, "ENGINE_DIR", test_engine_dir)
    monkeypatch.setattr(cfg, "STATE_DIR", state_dir)
    monkeypatch.setattr(cfg, "PAYLOADS_DIR", test_engine_dir / "payloads")
    monkeypatch.setattr(cfg, "BACKUP_DIR", test_engine_dir / "backup")
    monkeypatch.setattr(cfg, "RUNS_LOG_PATH", state_dir / "runs.jsonl")

    # Also patch logger RUNS_LOG_PATH
    import aryan_implementation.engine.logger as log_mod
    monkeypatch.setattr(log_mod, "RUNS_LOG_PATH", state_dir / "runs.jsonl")

    yield test_engine_dir
