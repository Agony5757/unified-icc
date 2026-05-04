from __future__ import annotations

from pathlib import Path

from unified_icc import utils


def test_unified_icc_dir_defaults_to_unified_icc_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("UNIFIED_ICC_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert utils.unified_icc_dir() == tmp_path / ".unified-icc"


def test_unified_icc_dir_prefers_unified_icc_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "custom"
    monkeypatch.setenv("UNIFIED_ICC_DIR", str(target))

    assert utils.unified_icc_dir() == target


def test_unified_icc_dir_ignores_old_dir_envs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("UNIFIED_ICC_DIR", raising=False)
    monkeypatch.setenv("CCLARK_CONFIG_DIR", str(tmp_path / "old-config"))
    monkeypatch.setenv("CCLARK_DIR", str(tmp_path / "old-dir"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert utils.unified_icc_dir() == tmp_path / ".unified-icc"
