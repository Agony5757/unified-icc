"""Tests for process_detection module."""

import pytest

from unified_icc.providers.process_detection import classify_provider_from_args


class TestClassifyProviderFromArgs:
    """Tests for classify_provider_from_args function."""

    def test_detects_claude(self):
        """Should detect claude from command line."""
        result = classify_provider_from_args("/usr/bin/claude --permission-mode default")
        assert result == "claude"

    def test_detects_claude_short_name(self):
        """Should detect claude from short name."""
        result = classify_provider_from_args("ce some-args")
        assert result == "claude"

    def test_detects_codex(self):
        """Should detect codex from command line."""
        result = classify_provider_from_args("codex --version")
        assert result == "codex"

    def test_detects_gemini(self):
        """Should detect gemini from command line."""
        result = classify_provider_from_args("gemini-cli --help")
        assert result == "gemini"

    def test_detects_pi(self):
        """Should detect pi from command line."""
        result = classify_provider_from_args("pi --version")
        assert result == "pi"

    def test_skips_first_wrapper_but_returns_provider(self):
        """Should skip first wrapper token and return the provider."""
        # When node is first, it should be skipped and next token returned
        result = classify_provider_from_args("node ce some-args")
        assert result == "claude"

        result = classify_provider_from_args("npx ce some-args")
        assert result == "claude"

    def test_handles_npm_global_install(self):
        """Should detect from npm global install path."""
        result = classify_provider_from_args(
            "/usr/local/bin/claude-code --permission-mode default"
        )
        assert result == "claude"

    def test_handles_yarn_global_install(self):
        """Should detect from yarn global install path."""
        result = classify_provider_from_args(
            "/home/user/.yarn/bin/claude-code"
        )
        assert result == "claude"

    def test_returns_shell_for_shell_commands(self):
        """Should return 'shell' for shell commands."""
        # bash is a known shell
        result = classify_provider_from_args("bash -c 'some command'")
        assert result == "shell"

        result = classify_provider_from_args("zsh -c 'some command'")
        assert result == "shell"

    def test_returns_empty_for_empty_args(self):
        """Should return empty string for empty args."""
        result = classify_provider_from_args("")
        assert result == ""

        result = classify_provider_from_args(None)  # type: ignore
        assert result == ""

    def test_handles_long_paths(self):
        """Should extract provider from long paths."""
        result = classify_provider_from_args(
            "/home/user/.npm-global/lib/node_modules/@anthropic/claude-code/bin/claude"
        )
        assert result == "claude"

    def test_handles_codex_path_markers(self):
        """Should detect codex from path markers."""
        result = classify_provider_from_args("/some/path/codex/index.js")
        assert result == "codex"

        result = classify_provider_from_args("/codex/script.js")
        assert result == "codex"

    def test_handles_pi_path_markers(self):
        """Should detect pi from path markers."""
        result = classify_provider_from_args("/some/path/pi-coding-agent/script.js")
        assert result == "pi"

    def test_handles_dashed_provider_names(self):
        """Should detect providers with dash prefix in name."""
        result = classify_provider_from_args("claude-code --version")
        assert result == "claude"

    def test_returns_empty_for_unknown_provider(self):
        """Should return empty string for unknown providers."""
        result = classify_provider_from_args("some-unknown-command")
        assert result == ""

    def test_all_wrapper_tokens_are_skipped(self):
        """All wrapper tokens should be skipped."""
        wrappers = ["sudo", "env", "node", "bun", "npx", "bunx", "uv", "python", "python3"]

        for wrapper in wrappers:
            result = classify_provider_from_args(f"{wrapper} claude")
            # Should skip wrapper and return claude
            assert result == "claude", f"Failed for wrapper: {wrapper}"
