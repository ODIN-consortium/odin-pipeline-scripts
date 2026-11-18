"""Tests for fallback_to_default_config in scripts/config_utils.sh."""

import shutil
import subprocess
from pathlib import Path

import pytest

CONFIG_UTILS = Path(__file__).resolve().parent.parent / "scripts" / "config_utils.sh"

# The full path matters on Windows: a bare "bash" can start WSL's bash.exe from
# System32 instead of the bash found on PATH.
BASH = shutil.which("bash")

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(BASH is None, reason="bash not available"),
]


def _fallback(tmp_path, default_lines, var_name, preset=None):
    """Source config_utils.sh with a temporary default config; return (home, value).

    The script runs from tmp_path and refers to its files relative to it, so no
    drive-letter path has to be understood by bash.
    """
    shutil.copy(CONFIG_UTILS, tmp_path / "config_utils.sh")
    (tmp_path / "default_paths.txt").write_text(
        "\n".join(default_lines) + "\n", encoding="utf-8"
    )
    preset_line = f"{var_name}={preset!r}" if preset is not None else f"unset {var_name}"
    script = f"""
        set -e
        export HOME="$PWD"
        SCRIPT_DIR="$PWD"
        USER_CONFIG="$PWD/user/odin_paths.txt"
        DEFAULT_CONFIG="$PWD/default_paths.txt"
        OLD_CONFIG="$PWD/missing.txt"
        source ./config_utils.sh
        {preset_line}
        fallback_to_default_config {var_name}
        printf '%s|%s' "$HOME" "${{{var_name}}}"
    """
    result = subprocess.run(
        [BASH, "-s"], input=script, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    home, _, value = result.stdout.partition("|")
    return home, value


def test_fallback_removes_quotes_and_expands_home(tmp_path):
    home, value = _fallback(tmp_path, ['output_dir="${HOME}/ODIN/data"'], "output_dir")
    assert value == f"{home}/ODIN/data"


def test_fallback_handles_unquoted_value(tmp_path):
    _, value = _fallback(tmp_path, ["output_dir=/srv/odin/data"], "output_dir")
    assert value == "/srv/odin/data"


def test_fallback_keeps_existing_value(tmp_path):
    _, value = _fallback(
        tmp_path, ['output_dir="${HOME}/ODIN/data"'], "output_dir", preset="/already/set"
    )
    assert value == "/already/set"


def test_fallback_leaves_unknown_setting_empty(tmp_path):
    _, value = _fallback(tmp_path, ['output_dir="${HOME}/ODIN/data"'], "metadata_file")
    assert value == ""


def test_shipped_defaults_resolve_without_quotes(tmp_path):
    shipped = (CONFIG_UTILS.parent / "odin_paths.txt").read_text(encoding="utf-8")
    lines = [line for line in shipped.splitlines() if line.startswith("minknow_data_dir=")]
    home, value = _fallback(tmp_path, lines, "minknow_data_dir")
    assert value == f"{home}/ODIN/minknow_output/"
