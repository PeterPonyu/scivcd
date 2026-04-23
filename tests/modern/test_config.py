"""Tests for ScivcdConfig — defaults, from_toml, from_pyproject, discover.

Skips gracefully if ScivcdConfig is not yet implemented.
"""

from __future__ import annotations

import textwrap
import pytest
from pathlib import Path

scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
if not hasattr(scivcd, "ScivcdConfig"):
    pytest.skip("ScivcdConfig not yet implemented", allow_module_level=True)

ScivcdConfig = scivcd.ScivcdConfig


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestScivcdConfigDefaults:
    def test_instantiates_without_arguments(self):
        cfg = ScivcdConfig()
        assert cfg is not None

    def test_disabled_checks_defaults_to_empty(self):
        cfg = ScivcdConfig()
        assert not cfg.disabled_checks

    def test_default_severity_floor_present(self):
        cfg = ScivcdConfig()
        # severity_floor controls which findings are suppressed.
        assert hasattr(cfg, "severity_floor")


# ---------------------------------------------------------------------------
# from_toml round-trip
# ---------------------------------------------------------------------------

class TestFromToml:
    def test_from_toml_round_trips_disabled_checks(self, tmp_path: Path):
        if not hasattr(ScivcdConfig, "from_toml"):
            pytest.skip("ScivcdConfig.from_toml not yet implemented")
        toml_content = textwrap.dedent("""\
            [scivcd]
            disabled_checks = ["layout.axis_overflow", "typography.min_font"]
        """)
        toml_file = tmp_path / "scivcd.toml"
        toml_file.write_text(toml_content)
        cfg = ScivcdConfig.from_toml(toml_file)
        assert "layout.axis_overflow" in cfg.disabled_checks
        assert "typography.min_font" in cfg.disabled_checks

    def test_from_toml_empty_file_gives_defaults(self, tmp_path: Path):
        if not hasattr(ScivcdConfig, "from_toml"):
            pytest.skip("ScivcdConfig.from_toml not yet implemented")
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        cfg = ScivcdConfig.from_toml(toml_file)
        assert cfg is not None
        assert not cfg.disabled_checks


# ---------------------------------------------------------------------------
# from_pyproject
# ---------------------------------------------------------------------------

class TestFromPyproject:
    def test_from_pyproject_reads_tool_scivcd_section(self, tmp_path: Path):
        if not hasattr(ScivcdConfig, "from_pyproject"):
            pytest.skip("ScivcdConfig.from_pyproject not yet implemented")
        pyproject = textwrap.dedent("""\
            [tool.scivcd]
            disabled_checks = ["content.annotation_data_overlap"]
        """)
        pyproject_file = tmp_path / "pyproject.toml"
        pyproject_file.write_text(pyproject)
        cfg = ScivcdConfig.from_pyproject(pyproject_file)
        assert "content.annotation_data_overlap" in cfg.disabled_checks

    def test_from_pyproject_absent_section_gives_defaults(self, tmp_path: Path):
        if not hasattr(ScivcdConfig, "from_pyproject"):
            pytest.skip("ScivcdConfig.from_pyproject not yet implemented")
        pyproject = textwrap.dedent("""\
            [tool.black]
            line-length = 88
        """)
        pyproject_file = tmp_path / "pyproject.toml"
        pyproject_file.write_text(pyproject)
        cfg = ScivcdConfig.from_pyproject(pyproject_file)
        assert cfg is not None
        assert not cfg.disabled_checks


# ---------------------------------------------------------------------------
# discover — walks upward from CWD (no arguments)
# ---------------------------------------------------------------------------

class TestDiscover:
    def test_discover_returns_a_config(self):
        """discover() takes no arguments and always returns a ScivcdConfig."""
        if not hasattr(ScivcdConfig, "discover"):
            pytest.skip("ScivcdConfig.discover not yet implemented")
        cfg = ScivcdConfig.discover()
        assert isinstance(cfg, ScivcdConfig)

    def test_discover_result_has_disabled_checks(self):
        """Whatever discover() returns, it must have a disabled_checks attribute."""
        if not hasattr(ScivcdConfig, "discover"):
            pytest.skip("ScivcdConfig.discover not yet implemented")
        cfg = ScivcdConfig.discover()
        assert hasattr(cfg, "disabled_checks")
