"""add_pathogens labels a pathogen-list TaxID and its descendants — and nothing else.

Descent comes from the report tree itself, via the indentation Kraken2 writes into the
scientific name — not from equality of the Root…Species *name* columns. A sub-species
row carries the same Species name as its parent, so matching on names gives a serovar
entry the same mask as its species entry; whichever comes later in the list wins, and
every *Salmonella enterica* row takes the serovar's label.

"""

import logging
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from kraken_parser import (  # noqa: E402
    DEPTH_COLUMN,
    LINEAGE_TAXIDS_COLUMN,
    RANK_COLUMN_MAPPING,
    enrich_kraken2_lineage,
    read_kraken2_report,
)
from create_kraken_datasets import add_pathogens, kraken2_to_dataframe  # noqa: E402

COLUMN_NAMES = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                'Rank code', 'NCBI tax ID', 'Scientific name']

# Salmonella with two serovars (one with a strain beneath it) and a sibling species,
# then Vibrio cholerae with two serogroup children — the two shapes that matter.
REPORT = (
    " 90.00\t900\t900\tU\t0\tunclassified\n"
    " 10.00\t100\t0\tR\t1\troot\n"
    " 10.00\t100\t0\tR1\t131567\t  cellular organisms\n"
    " 10.00\t100\t0\tR2\t2\t    Bacteria\n"
    " 10.00\t100\t0\tP\t1224\t      Pseudomonadota\n"
    " 10.00\t100\t0\tC\t1236\t        Gammaproteobacteria\n"
    "  8.00\t80\t0\tO\t91347\t          Enterobacterales\n"
    "  8.00\t80\t0\tF\t543\t            Enterobacteriaceae\n"
    "  8.00\t80\t2\tG\t590\t              Salmonella\n"
    "  7.00\t70\t10\tS\t28901\t                Salmonella enterica\n"
    "  4.00\t40\t30\tS1\t59201\t                  Salmonella enterica subsp. enterica\n"
    "  3.00\t30\t20\tS2\t90370\t                    Salmonella enterica subsp. enterica serovar Typhi\n"
    "  1.00\t10\t10\tS3\t220341\t                      Salmonella enterica subsp. enterica serovar Typhi str. CT18\n"
    "  1.00\t10\t10\tS2\t90371\t                    Salmonella enterica subsp. enterica serovar Typhimurium\n"
    "  0.80\t8\t8\tS\t54736\t                Salmonella bongori\n"
    "  2.00\t20\t0\tO\t135623\t          Vibrionales\n"
    "  2.00\t20\t0\tF\t641\t            Vibrionaceae\n"
    "  2.00\t20\t0\tG\t662\t              Vibrio\n"
    "  2.00\t20\t5\tS\t666\t                Vibrio cholerae\n"
    "  1.00\t10\t10\tS1\t127906\t                  Vibrio cholerae O1\n"
    "  0.50\t5\t5\tS1\t45888\t                  Vibrio cholerae O139\n"
)

ENTERICA_CLADE = {28901, 59201, 90370, 220341, 90371}
TYPHI_CLADE = {90370, 220341}


def _report(tmp_path: Path, name: str = "barcode01.kraken2.report.txt") -> str:
    path = tmp_path / name
    path.write_text(REPORT)
    return str(path)


def _yaml(tmp_path: Path, entries: list[tuple[int, str, str]]) -> str:
    """entries: (taxid, scientific_name, pathogen_group) in list order."""
    text = "pathogens:\n" + "".join(
        f'  - taxid: {taxid}\n    scientific_name: "{name}"\n    type: bacteria\n'
        f'    target_group: waterborne\n    pathogen_group: "{group}"\n'
        for taxid, name, group in entries
    )
    path = tmp_path / "pathogens.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _groups(df: pd.DataFrame) -> dict:
    return dict(zip(df["NCBI tax ID"], df["Priority pathogen group"]))


def _rows(tmp_path: Path, name: str = "barcode01.kraken2.report.txt") -> pd.DataFrame:
    return kraken2_to_dataframe(_report(tmp_path, name), COLUMN_NAMES)


# ── parser: depth and lineage TaxIDs ─────────────────────────────────────────


@pytest.mark.unit
def test_read_report_records_the_depth_from_the_indentation(tmp_path):
    df = read_kraken2_report(_report(tmp_path), COLUMN_NAMES)

    depth = dict(zip(df["NCBI tax ID"], df[DEPTH_COLUMN]))
    assert depth[0] == 0 and depth[1] == 0          # unclassified and root
    assert depth[131567] == 1 and depth[2] == 2
    assert depth[590] == 7 and depth[28901] == 8 and depth[90370] == 10
    assert depth[54736] == 8                         # sibling species back at the species depth
    assert df["Scientific name"].tolist()[2] == "cellular organisms"   # names still stripped


@pytest.mark.unit
def test_lineage_taxids_follow_the_report_tree(tmp_path):
    df = enrich_kraken2_lineage(read_kraken2_report(_report(tmp_path), COLUMN_NAMES), RANK_COLUMN_MAPPING)

    lineage = dict(zip(df["NCBI tax ID"], df[LINEAGE_TAXIDS_COLUMN]))
    assert lineage[90370] == "1;131567;2;1224;1236;91347;543;590;28901;59201;90370"
    assert lineage[54736] == "1;131567;2;1224;1236;91347;543;590;54736"       # not via 28901
    assert lineage[127906] == "1;131567;2;1224;1236;135623;641;662;666;127906"  # sibling branch popped
    assert lineage[0] == "0"


@pytest.mark.unit
def test_frames_without_depth_get_no_lineage_taxids():
    """Callers that hand-build a frame (existing tests, ad-hoc use) still work."""
    df = pd.DataFrame([{"Rank code": "S", "Scientific name": "Monkeypox virus"}])

    enriched = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

    assert LINEAGE_TAXIDS_COLUMN not in enriched.columns
    assert enriched.loc[0, "Species"] == "Monkeypox virus"


# ── add_pathogens ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_serovar_entry_does_not_relabel_its_parent_clade(tmp_path):
    """Typhi is listed *first*, so a passing result also shows that list order does not
    decide the outcome."""
    pathogens = _yaml(tmp_path, [
        (90370, "Salmonella enterica subsp. enterica serovar Typhi", "Salmonella Typhi"),
        (28901, "Salmonella enterica", "Salmonella enterica"),
    ])

    groups = _groups(add_pathogens(_rows(tmp_path), pathogens))

    assert {t for t, g in groups.items() if g == "Salmonella Typhi"} == TYPHI_CLADE
    assert {t for t, g in groups.items() if g == "Salmonella enterica"} == ENTERICA_CLADE - TYPHI_CLADE
    assert groups[590] is None and groups[54736] is None   # genus node and sibling species untouched


@pytest.mark.unit
@pytest.mark.parametrize("genus_first", [True, False])
def test_genus_and_species_entries_nest_the_same_way_in_either_order(tmp_path, genus_first, caplog):
    entries = [(590, "Salmonella", "MDR Salmonella spp"), (28901, "Salmonella enterica", "Salmonella enterica")]
    pathogens = _yaml(tmp_path, entries if genus_first else entries[::-1])

    with caplog.at_level(logging.WARNING, logger="create_kraken_datasets"):
        groups = _groups(add_pathogens(_rows(tmp_path), pathogens))

    assert {t for t, g in groups.items() if g == "Salmonella enterica"} == ENTERICA_CLADE
    assert {t for t, g in groups.items() if g == "MDR Salmonella spp"} == {590, 54736}
    assert "nested under another entry" in caplog.text and "28901" in caplog.text


@pytest.mark.unit
def test_sibling_serogroup_entries_do_not_capture_the_species_node(tmp_path):
    """An entry for a serogroup labels that serogroup, not the species node above it.

    Name matching would give the O1/O139 entries the reads assigned directly to
    *V. cholerae* (666) as well. Whether 666 belongs in the group is a decision for the
    pathogen list to state, not a side effect of how descendants are found."""
    pathogens = _yaml(tmp_path, [
        (127906, "Vibrio cholerae O1", "Vibrio cholerae"),
        (45888, "Vibrio cholerae O139", "Vibrio cholerae"),
    ])

    groups = _groups(add_pathogens(_rows(tmp_path), pathogens))

    assert groups[127906] == "Vibrio cholerae" and groups[45888] == "Vibrio cholerae"
    assert groups[666] is None and groups[662] is None


@pytest.mark.unit
def test_species_entry_labels_its_whole_clade(tmp_path):
    """The shape pathogen_group_map.yaml relies on today (one entry per lineage) still works."""
    pathogens = _yaml(tmp_path, [(28901, "Salmonella enterica", "Salmonella spp.")])

    groups = _groups(add_pathogens(_rows(tmp_path), pathogens))

    assert {t for t, g in groups.items() if g == "Salmonella spp."} == ENTERICA_CLADE


@pytest.mark.unit
def test_root_or_unclassified_entry_is_refused(tmp_path):
    """An entry at root or unclassified would match every row, so it is refused."""
    pathogens = _yaml(tmp_path, [(1, "root", "everything")])

    with pytest.raises(ValueError, match="would label every row"):
        add_pathogens(_rows(tmp_path), pathogens)


@pytest.mark.unit
def test_invisible_characters_and_surrounding_whitespace_are_stripped_from_labels(tmp_path):
    """A label differing from another only by a trailing U+200B or a trailing space is a
    different group to every consumer while looking identical in an editor, so the reader
    never lets one through."""
    from create_kraken_datasets import read_pathogens
    zwsp = "​"
    p = tmp_path / "pathogens.yaml"
    p.write_text(
        f'pathogens:\n  - taxid: 573\n    pathogen_group: "ESBL/Carbapenemase producing K. pneumoniae{zwsp}"\n'
        f'    scientific_name: " Klebsiella pneumoniae "\n    type: bacteria\n    target_group: AMR\n'
        f'  - taxid: 5807\n    pathogen_group: "Cryptosporidium "\n    type: eukaryotic\n    target_group: waterborne\n',
        encoding="utf-8",
    )

    df = read_pathogens(str(p))

    assert df["Priority pathogen group"].tolist() == ["ESBL/Carbapenemase producing K. pneumoniae", "Cryptosporidium"]
    assert df["scientific name"].iloc[0] == "Klebsiella pneumoniae"


@pytest.mark.unit
def test_entries_absent_from_the_data_are_skipped(tmp_path):
    pathogens = _yaml(tmp_path, [(10244, "Monkeypox virus", "Mpox virus")])

    df = add_pathogens(_rows(tmp_path), pathogens)

    assert df["Priority pathogen group"].isna().all()


@pytest.mark.unit
def test_helper_columns_are_dropped_and_lineage_names_kept(tmp_path):
    pathogens = _yaml(tmp_path, [(28901, "Salmonella enterica", "Salmonella spp.")])

    df = add_pathogens(_rows(tmp_path), pathogens)

    assert DEPTH_COLUMN not in df.columns and LINEAGE_TAXIDS_COLUMN not in df.columns
    assert list(RANK_COLUMN_MAPPING.values()) == [c for c in df.columns if c in RANK_COLUMN_MAPPING.values()]
    assert set(df.columns) >= {"Type", "Priority", "Target group", "Priority pathogen group"}


@pytest.mark.unit
def test_frames_without_lineage_taxids_are_rejected(tmp_path):
    pathogens = _yaml(tmp_path, [(28901, "Salmonella enterica", "Salmonella spp.")])
    df = pd.DataFrame([{"NCBI tax ID": 28901, "Rank code": "S", "Scientific name": "Salmonella enterica"}])

    with pytest.raises(ValueError, match=LINEAGE_TAXIDS_COLUMN):
        add_pathogens(df, pathogens)


@pytest.mark.unit
def test_concatenated_reports_with_a_duplicated_index_are_labelled_per_file(tmp_path):
    """create_kraken_dataset concatenates per-file frames without resetting the index."""
    pathogens = _yaml(tmp_path, [(90370, "Salmonella Typhi", "Salmonella Typhi")])
    both = pd.concat([_rows(tmp_path, "barcode01.kraken2.report.txt"),
                      _rows(tmp_path, "barcode02.kraken2.report.txt")], axis=0)
    assert both.index.has_duplicates

    df = add_pathogens(both, pathogens)

    labelled = df.loc[df["Priority pathogen group"].notna(), "NCBI tax ID"]
    assert sorted(labelled) == sorted(list(TYPHI_CLADE) * 2)
