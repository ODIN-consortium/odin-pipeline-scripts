"""Tests for scripts/amr_kraken2_db.py: the local Kraken2 database and taxonomy of an AMR run."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from amr_kraken2_db import main, resolve


def _db(base: Path, name: str, bracken: bool = True, taxonomy: bool = True) -> Path:
    d = base / name
    d.mkdir()
    (d / "hash.k2d").write_text("")
    if bracken:
        (d / "database150mers.kmer_distrib").write_text("")
    if taxonomy:
        (d / "taxonomy").mkdir()
        (d / "taxonomy" / "names.dmp").write_text("")
        (d / "taxonomy" / "nodes.dmp").write_text("")
    return d


def _csv(path: Path, *dirs: Path, tool: str = "kraken2") -> str:
    lines = ["tool,db_name,db_params,db_path"] + [f"{tool},db{i},--quick,{d}" for i, d in enumerate(dirs)]
    path.write_text("\n".join(lines) + "\n")
    return str(path)


@pytest.mark.unit
def test_download_keeps_the_downloaded_database(tmp_path):
    assert resolve("download", _csv(tmp_path / "d.csv", _db(tmp_path, "a"))) == ("", "")
    assert resolve("DOWNLOAD") == ("", "")


@pytest.mark.unit
def test_explicit_directory_gives_database_and_taxonomy(tmp_path):
    db = _db(tmp_path, "a")
    assert resolve(str(db)) == (str(db), str(db / "taxonomy"))


@pytest.mark.unit
def test_taxonomy_omitted_without_names_and_nodes(tmp_path):
    db = _db(tmp_path, "a", taxonomy=False)
    assert resolve(str(db)) == (str(db), "")


@pytest.mark.unit
def test_explicit_directory_must_exist(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        resolve(str(tmp_path / "nowhere"))


@pytest.mark.unit
def test_explicit_directory_needs_a_bracken_file(tmp_path):
    with pytest.raises(ValueError, match="no Bracken file"):
        resolve(str(_db(tmp_path, "a", bracken=False)))


@pytest.mark.unit
def test_empty_setting_uses_the_databases_csv(tmp_path):
    db = _db(tmp_path, "a")
    assert resolve("", _csv(tmp_path / "d.csv", db)) == (str(db), str(db / "taxonomy"))


@pytest.mark.unit
def test_databases_csv_row_without_bracken_file_is_not_used(tmp_path):
    assert resolve("", _csv(tmp_path / "d.csv", _db(tmp_path, "a", bracken=False))) == ("", "")


@pytest.mark.unit
def test_only_kraken2_rows_count(tmp_path):
    assert resolve("", _csv(tmp_path / "d.csv", _db(tmp_path, "a"), tool="centrifuge")) == ("", "")


@pytest.mark.unit
def test_no_databases_csv_means_download(tmp_path):
    assert resolve("", "") == ("", "")
    assert resolve("", str(tmp_path / "missing.csv")) == ("", "")


@pytest.mark.unit
def test_two_usable_databases_is_ambiguous(tmp_path):
    csv_file = _csv(tmp_path / "d.csv", _db(tmp_path, "a"), _db(tmp_path, "b"))
    with pytest.raises(ValueError, match="More than one"):
        resolve("", csv_file)


@pytest.mark.unit
def test_cli_prints_database_then_taxonomy_and_fails_with_a_message(tmp_path, capsys):
    db = _db(tmp_path, "a")
    assert main(["--setting", str(db)]) == 0
    assert capsys.readouterr().out.splitlines() == [str(db), str(db / "taxonomy")]
    assert main(["--setting", str(tmp_path / "nowhere")]) == 1
    assert "not found" in capsys.readouterr().err
