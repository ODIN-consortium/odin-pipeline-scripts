"""
Unit tests for parse_amr_json.py module.

Tests cover:
- Parsing AMR JSON files
- Finding AMR files for barcodes
- Merging with sites data
- Summary creation
"""

import logging

import pytest
import pandas as pd
import json
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from parse_amr_json import (
    parse_amr_json_file,
    _find_amr_files_for_barcode,
    merge_with_sites_df,
    create_summary,
    summarise_by_resistance,
    finish_amr_columns,
    AMR_COLUMNS,
    _make_drug_code,
    assign_drug_codes,
    add_short_names,
)





class TestDrugCodes:
    """short_name: a display abbreviation of `resistance`, assigned per dataset.

    Nothing about the drug-class vocabulary is hard-coded, so a study with entirely
    different classes is handled the same way. Codes are handed out over the sorted
    set of classes present, so the same set always yields the same mapping.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("name,expected", [
        ("fluoroquinolone", "flrq"), ("carbapenem", "crbp"),
        ("cephalosporin", "cphl"), ("cephamycin", "cphm"),
        ("aminoglycoside", "amng"), ("aminocoumarin", "amnc"),
        ("glycopeptide", "glcp"), ("glycylcycline", "glcl"),
        ("nitroimidazole", "ntrm"), ("nitrofuran", "ntrf"),
    ])
    def test_a_lone_class_gets_first_letter_plus_three_consonants(self, name, expected):
        assert _make_drug_code(name) == expected

    @pytest.mark.unit
    def test_y_is_a_vowel_so_the_glyco_classes_differ(self):
        """Regression: with 'y' as a consonant both gave 'glyc'.

        Glycopeptide (cell wall, e.g. vancomycin) and glycylcycline (protein
        synthesis, e.g. tigecycline) are different drug classes.
        """
        assert _make_drug_code("glycopeptide") != _make_drug_code("glycylcycline")

    @pytest.mark.unit
    def test_a_class_with_too_few_consonants_falls_back_to_its_name(self):
        """'penam' and 'penem' share the skeleton 'pnm'; the plain name separates them."""
        codes = assign_drug_codes(["penam", "penem"])
        assert codes["penam"] != codes["penem"]
        assert {len(c) for c in codes.values()} == {4}

    @pytest.mark.unit
    def test_a_clash_swaps_the_fourth_character_rather_than_growing(self):
        codes = assign_drug_codes(["cephalosporin", "cephalexin"])
        assert set(codes.values()) == {"cphl", "cphs"}
        assert {len(c) for c in codes.values()} == {4}

    @pytest.mark.unit
    def test_codes_lengthen_only_once_the_four_character_forms_run_out(self):
        """Names with the same consonant skeleton exhaust cphl/cphx/cphn first."""
        names = ["cephalexin", "cephalexina", "cephalexine", "cephalexino"]
        codes = assign_drug_codes(names)
        assert len(set(codes.values())) == len(names)
        assert max(len(c) for c in codes.values()) > 4

    @pytest.mark.unit
    def test_the_same_set_always_yields_the_same_mapping(self):
        """Names are sorted before codes are assigned, so file order cannot matter."""
        names = ["tetracycline", "cephalexin", "cephalosporin", "penam", "penem"]
        first = assign_drug_codes(names)
        for shuffled in ([*reversed(names)], sorted(names), names[2:] + names[:2]):
            assert assign_drug_codes(shuffled) == first

    @pytest.mark.unit
    def test_a_code_widens_only_when_the_clashing_class_is_present(self):
        """The trade-off of having no fixed vocabulary, pinned so it stays deliberate."""
        assert assign_drug_codes(["cephalosporin"])["cephalosporin"] == "cphl"
        assert assign_drug_codes(["cephalosporin", "cephalexin"])["cephalosporin"] == "cphs"

    @pytest.mark.unit
    def test_short_names_are_assigned_across_the_whole_dataset(self):
        """One file's classes must not decide the codes another file's rows get."""
        df = pd.DataFrame({"resistance": ["cephalosporin;tetracycline", "cephalexin", None]})

        out = add_short_names(df)

        assert out.loc[0, "short_name"] == "cphs;ttrc"
        assert out.loc[1, "short_name"] == "cphl"
        assert pd.isna(out.loc[2, "short_name"])

    @pytest.mark.unit
    def test_an_empty_frame_is_returned_untouched(self):
        assert add_short_names(pd.DataFrame()).empty

    @pytest.mark.unit
    def test_a_collision_never_stops_the_data_being_written(self, caplog):
        """short_name is a convenience; `resistance` is always unambiguous."""
        df = pd.DataFrame({"resistance": ["cephalexin", "cephalexin "]})

        with caplog.at_level(logging.WARNING):
            out = add_short_names(df)

        assert len(out) == 2
        assert out["short_name"].notna().all()
#: A Kraken2 report with 500 classified and 500 unclassified reads. The parser requires
#: one beside every AMR JSON: read totals are the denominator for rpm, and a row without
#: them could never be normalised.
ROOT_REPORT = (
    " 50.00\t500\t500\tU\t0\tunclassified\n"
    " 50.00\t500\t2\tR\t1\troot\n"
    " 49.80\t498\t498\tD\t2\t  Bacteria\n"
)


def _amr_run(tmp_path, data, name="test", barcodes=("barcode01",), report=ROOT_REPORT):
    """Lay out one wf-metagenomics AMR run and return the path of its JSON.

    The parser looks for ``<run>/kraken2/<barcode>.kraken2.report.txt`` beside
    ``<run>/amr/<barcode>.amr.json``, so the directory shape matters.
    """
    run = tmp_path / "run"
    (run / "amr").mkdir(parents=True, exist_ok=True)
    json_path = run / "amr" / f"{name}.amr.json"
    with open(json_path, 'w') as f:
        json.dump(data, f)
    if report is not None:
        (run / "kraken2").mkdir(parents=True, exist_ok=True)
        for barcode in barcodes:
            (run / "kraken2" / f"{barcode}.kraken2.report.txt").write_text(report)
    return str(json_path)


class TestParseAmrJsonFile:
    """Tests for parse_amr_json_file function."""

    @pytest.mark.unit
    def test_parse_simple_json(self, tmp_path):
        """Test parsing a simple AMR JSON file."""
        # Create test JSON file
        test_data = {
            "barcode01": {
                "pass": True,
                "results": {
                    "gene1": {
                        "count": 5,
                        "meta": [
                            {
                                "RESISTANCE": "ampicillin",
                                "SEQUENCE": "ATCGATCG",
                                "START": 100,
                                "END": 200,
                                "%COVERAGE": 95.5,
                                "%IDENTITY": 99.2
                            }
                        ]
                    }
                }
            }
        }

        path = _amr_run(tmp_path, test_data)

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['run_accession'] == "RUN001"
        assert records[0]['barcode'] == "barcode01"
        assert records[0]['pass_status'] == True
        assert records[0]['gene_description'] == "gene1"
        assert records[0]['resistance'] == "ampicillin"
        # The JSON's "count" is the gene's total, repeated on every entry of its "meta"
        # list. The parser ignores it and counts the entries, so that summing rows does
        # not square the total. One alignment of one read:
        assert records[0]['read_count'] == 1
        assert records[0]['alignment_count'] == 1
        assert records[0]['coverage_percent'] == 95.5
        assert records[0]['identity_percent'] == 99.2
        assert records[0]['classified_reads'] == 500
        assert records[0]['total_reads'] == 1000

    @pytest.mark.unit
    def test_parse_multi_resistance(self, tmp_path):
        """Test parsing JSON with multiple resistance markers."""
        test_data = {
            "barcode01": {
                "pass": True,
                "results": {
                    "gene1": {
                        "count": 3,
                        "meta": [
                            {
                                "RESISTANCE": "ampicillin;tetracycline;chloramphenicol",
                                "SEQUENCE": "ATCG",
                                "START": 50,
                                "END": 150,
                                "%COVERAGE": 90.0,
                                "%IDENTITY": 98.5
                            }
                        ]
                    }
                }
            }
        }

        path = _amr_run(tmp_path, test_data, name="test_multi")

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['multi_resistance'] == True
        assert records[0]['resistance'] == "ampicillin;tetracycline;chloramphenicol"
        # short_name is filled later, over the whole dataset (see TestDrugCodes)
        assert records[0]['short_name'] is None

    @pytest.mark.unit
    def test_parse_multiple_barcodes(self, tmp_path):
        """Test parsing JSON with multiple barcodes."""
        test_data = {
            "barcode01": {
                "pass": True,
                "results": {
                    "gene1": {
                        "count": 2,
                        "meta": [{"RESISTANCE": "ampicillin", "SEQUENCE": "ATCG", "START": 1, "END": 100, "%COVERAGE": 95.0, "%IDENTITY": 99.0}]
                    }
                }
            },
            "barcode02": {
                "pass": False,
                "results": {
                    "gene2": {
                        "count": 1,
                        "meta": [{"RESISTANCE": "tetracycline", "SEQUENCE": "GCTA", "START": 1, "END": 100, "%COVERAGE": 92.0, "%IDENTITY": 97.0}]
                    }
                }
            }
        }

        path = _amr_run(
            tmp_path, test_data, name="test_multi_barcode",
            barcodes=("barcode01", "barcode02"),
        )

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert len(records) == 2
        assert records[0]['barcode'] == "barcode01"
        assert records[0]['pass_status'] == True
        assert records[1]['barcode'] == "barcode02"
        assert records[1]['pass_status'] == False

    @pytest.mark.unit
    def test_a_barcode_with_no_gene_becomes_one_row_carrying_its_read_totals(self, tmp_path):
        """abricate writes pass: false when its results table is empty, so such a barcode
        was analysed and carried no resistance gene. The row is what lets a denominator
        count it; without it every count is of barcodes that detected something."""
        path = _amr_run(tmp_path, {"barcode01": {"pass": False}}, name="test_empty")

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['pass_status'] is False
        assert records[0]['resistance'] is None
        assert records[0]['gene_description'] is None
        assert records[0]['classified_reads'] == 500
        assert records[0]['total_reads'] == 1000

    @pytest.mark.unit
    def test_a_barcode_with_no_gene_has_zero_reads_not_a_missing_count(self, tmp_path):
        """Consumers filter on read_count before they touch resistance, and one of them
        raises on a missing count rather than dropping the row as below threshold."""
        path = _amr_run(tmp_path, {"barcode01": {"pass": False}}, name="test_empty")

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert records[0]['read_count'] == 0
        assert records[0]['alignment_count'] == 0

    @pytest.mark.unit
    def test_a_barcode_with_no_gene_and_no_report_is_skipped_not_written_empty(self, tmp_path, capsys):
        """"No gene in 47 reads" and "no gene in a million" are different findings, so a
        row without real totals would be worse than no row. It is reported, not silent."""
        path = _amr_run(tmp_path, {"barcode01": {"pass": False}}, name="test_empty", report=None)

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert records == []
        assert "no usable read total" in capsys.readouterr().out

    @pytest.mark.unit
    def test_the_rows_of_a_barcode_with_no_gene_have_the_same_columns(self, tmp_path):
        empty = parse_amr_json_file(
            _amr_run(tmp_path / "a", {"barcode01": {"pass": False}}), run_accession="RUN001"
        )[0]
        found = parse_amr_json_file(
            _amr_run(tmp_path / "b", {
                "barcode01": {
                    "pass": True,
                    "results": {"gene1": {"count": 1, "meta": [{
                        "RESISTANCE": "ampicillin", "SEQUENCE": "ATCG",
                        "START": 1, "END": 100, "%COVERAGE": 95.0, "%IDENTITY": 99.0,
                    }]}},
                }
            }), run_accession="RUN001",
        )[0]

        assert empty.keys() == found.keys()

    @pytest.mark.unit
    def test_parse_missing_resistance(self, tmp_path):
        """Test parsing JSON with missing RESISTANCE field."""
        test_data = {
            "barcode01": {
                "pass": True,
                "results": {
                    "gene1": {
                        "count": 1,
                        "meta": [
                            {
                                "SEQUENCE": "ATCG",
                                "START": 1,
                                "END": 100,
                                "%COVERAGE": 95.0,
                                "%IDENTITY": 99.0
                            }
                        ]
                    }
                }
            }
        }

        path = _amr_run(tmp_path, test_data, name="test_no_resistance")

        records = parse_amr_json_file(path, run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['resistance'] is None
        # short_name becomes empty string when there are no valid resistance tokens
        assert records[0]['short_name'] is None
        assert records[0]['multi_resistance'] == False

    @pytest.mark.unit
    def test_parse_invalid_json(self, tmp_path):
        """Test parsing an invalid JSON file."""
        json_file = tmp_path / "invalid.json"
        with open(json_file, 'w') as f:
            f.write("not valid json{")

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        # Should return empty list on error
        assert len(records) == 0


class TestFindAmrFilesForBarcode:
    """Tests for _find_amr_files_for_barcode function."""

    @pytest.mark.unit
    def test_find_single_file(self, tmp_path):
        """Test finding a single AMR file for a barcode."""
        # Create directory structure
        amr_dir = tmp_path / "amr"
        amr_dir.mkdir()
        amr_file = amr_dir / "barcode01.amr.json"
        amr_file.write_text("{}")

        files = _find_amr_files_for_barcode(str(tmp_path), "barcode01")

        assert len(files) == 1
        assert "barcode01.amr.json" in files[0]

    @pytest.mark.unit
    def test_find_nested_file(self, tmp_path):
        """Test finding AMR file in nested directory."""
        # Create nested directory structure
        nested_dir = tmp_path / "subdir" / "amr"
        nested_dir.mkdir(parents=True)
        amr_file = nested_dir / "barcode02.amr.json"
        amr_file.write_text("{}")

        files = _find_amr_files_for_barcode(str(tmp_path), "barcode02")

        assert len(files) == 1
        assert "barcode02.amr.json" in files[0]

    @pytest.mark.unit
    def test_no_files_found(self, tmp_path):
        """Test when no AMR files are found."""
        amr_dir = tmp_path / "amr"
        amr_dir.mkdir()

        files = _find_amr_files_for_barcode(str(tmp_path), "barcode99")

        assert len(files) == 0

    @pytest.mark.unit
    def test_multiple_files_deduplicated(self, tmp_path):
        """Test that duplicate files are deduplicated."""
        # This tests the deduplication logic in the function
        amr_dir = tmp_path / "amr"
        amr_dir.mkdir()
        amr_file = amr_dir / "barcode01.amr.json"
        amr_file.write_text("{}")

        files = _find_amr_files_for_barcode(str(tmp_path), "barcode01")

        # Should only return unique paths
        assert len(files) == len(set(files))


class TestMergeWithSitesDf:
    """Tests for merge_with_sites_df function."""

    @pytest.mark.unit
    def test_merge_with_valid_sites(self):
        """Test merging AMR data with sites information."""
        amr_df = pd.DataFrame({
            'sample_id': ['SITE01_WW_001', 'SITE02_TP_001'],
            'resistance': ['ampicillin', 'tetracycline']
        })

        sites_df = pd.DataFrame({
            'site_ID': ['SITE01', 'SITE02'],
            'country': ['USA', 'Canada'],
            'longitude': [-122.4194, -79.3832],
            'latitude': [37.7749, 43.6532]
        })

        result = merge_with_sites_df(amr_df, sites_df)

        assert 'country' in result.columns
        assert 'lon' in result.columns
        assert 'lat' in result.columns
        assert result.loc[result['sample_id'] == 'SITE01_WW_001', 'country'].iloc[0] == 'USA'
        assert result.loc[result['sample_id'] == 'SITE02_TP_001', 'country'].iloc[0] == 'Canada'

    @pytest.mark.unit
    def test_merge_with_empty_sites(self):
        """Test merging when sites dataframe is empty."""
        amr_df = pd.DataFrame({
            'sample_id': ['SITE01_WW_001'],
            'resistance': ['ampicillin']
        })

        sites_df = pd.DataFrame()

        result = merge_with_sites_df(amr_df, sites_df)

        # Should add columns with None values
        assert 'country' in result.columns
        assert result['country'].isna().all()

    @pytest.mark.unit
    def test_merge_with_missing_site(self):
        """Test merging when a site is not in sites dataframe."""
        amr_df = pd.DataFrame({
            'sample_id': ['SITE99_WW_001'],
            'resistance': ['ampicillin']
        })

        sites_df = pd.DataFrame({
            'site_ID': ['SITE01'],
            'country': ['USA'],
            'longitude': [-122.4194],
            'latitude': [37.7749]
        })

        result = merge_with_sites_df(amr_df, sites_df)

        # Should have columns but with None values for missing site
        assert 'country' in result.columns
        assert result['country'].isna().all()


class TestCreateSummary:
    """Tests for create_summary function."""

    @pytest.mark.unit
    def test_create_summary_basic(self, tmp_path):
        """Test creating a basic summary."""
        df = pd.DataFrame({
            'resistance': ['ampicillin', 'ampicillin', 'tetracycline'],
            'run_accession': ['RUN001', 'RUN002', 'RUN001'],
            'barcode': ['barcode01', 'barcode02', 'barcode01'],
            'read_count': [4, 2, 1],
            'alignment_count': [5, 2, 1],
            'sequence': ['ATCG', 'ATCG', 'GCTA'],
            'coverage_percent': [95.0, 96.0, 92.0],
            'identity_percent': [99.0, 99.5, 97.0],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_002', 'SITE01_WW_001']
        })

        create_summary(df, str(tmp_path), "test")

        # Check that summary file was created
        summary_file = tmp_path / "test_summary_by_resistance.csv"
        assert summary_file.exists()

        # Read and verify summary
        summary = pd.read_csv(summary_file).set_index('resistance')
        assert len(summary) == 2  # Two unique resistance types
        assert 'ampicillin' in summary.index
        assert 'tetracycline' in summary.index
        # Row counts, named apart from the read-count 'count' of the detection frame.
        assert summary.loc['ampicillin', 'n_detections'] == 2
        assert 'count' not in summary.columns

    @pytest.mark.unit
    def test_create_summary_no_output_dir(self):
        """Test creating summary without output directory."""
        df = pd.DataFrame({
            'resistance': ['ampicillin'],
            'run_accession': ['RUN001'],
            'barcode': ['barcode01'],
            'read_count': [4],
            'alignment_count': [5],
            'sequence': ['ATCG'],
            'coverage_percent': [95.0],
            'identity_percent': [99.0],
            'sample_id': ['SITE01_WW_001']
        })

        # Should not raise error when out_dir is None
        create_summary(df, None, None)


class TestPublishedLayout:
    """amr_data and its summary have the published column set and order."""

    @pytest.mark.unit
    def test_summary_columns_and_order(self):
        df = pd.DataFrame({
            'resistance': ['tetracycline', 'aminoglycoside', 'aminoglycoside'],
            'run_accession': ['RUN001', 'RUN001', 'RUN002'],
            'barcode': ['barcode01', 'barcode01', 'barcode02'],
            'read_count': [1, 4, 2],
            'alignment_count': [1, 5, 2],
            'coverage_percent': [92.0, 95.0, 96.0],
            'identity_percent': [97.0, 99.0, 99.5],
            'sample_code': ['SITE02_WW', 'SITE01_WW', 'SITE01_WW'],
        })
        summary = summarise_by_resistance(df)
        assert list(summary.columns) == ['resistance', 'n_detections', 'run_accession', 'barcode', 'read_count',
                                         'alignment_count', 'coverage_percent', 'identity_percent', 'sample_code']
        assert list(summary['resistance']) == ['aminoglycoside', 'tetracycline']
        row = summary.iloc[0]
        assert (row['n_detections'], row['run_accession'], row['read_count'], row['sample_code']) == (2, 2, 6, 'SITE01_WW')

    @pytest.mark.unit
    def test_finish_amr_columns(self):
        df = pd.DataFrame({c: ['x'] for c in AMR_COLUMNS if c not in ('sample_key', 'type')})
        df['sample_id'] = ['SITE01_WW_P2']
        df['sampling_date'] = ['20250903']
        df['type'] = [None]
        df = df[list(reversed(df.columns))]
        out = finish_amr_columns(df)
        assert list(out.columns) == AMR_COLUMNS
        assert out.loc[0, 'sample_key'] == 'SITE01_WW_P2_20250903'
        assert out.loc[0, 'type'] == ''

    @pytest.mark.unit
    def test_sample_key_empty_without_date(self):
        df = pd.DataFrame({'sample_id': ['SITE01_WW_P2'], 'sampling_date': [None]})
        assert finish_amr_columns(df).loc[0, 'sample_key'] == ''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

