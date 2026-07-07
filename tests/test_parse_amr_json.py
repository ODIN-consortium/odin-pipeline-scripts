"""
Unit tests for parse_amr_json.py module.

Tests cover:
- Parsing AMR JSON files
- Finding AMR files for barcodes
- Merging with sites data
- Summary creation
"""

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
)


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

        json_file = tmp_path / "test.amr.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['run_accession'] == "RUN001"
        assert records[0]['barcode'] == "barcode01"
        assert records[0]['pass_status'] == True
        assert records[0]['gene_description'] == "gene1"
        assert records[0]['resistance'] == "ampicillin"
        assert records[0]['count'] == 5
        assert records[0]['coverage_percent'] == 95.5
        assert records[0]['identity_percent'] == 99.2

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

        json_file = tmp_path / "test_multi.amr.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['multi_resistance'] == True
        assert records[0]['resistance'] == "ampicillin;tetracycline;chloramphenicol"
        assert records[0]['short_name'] == "ampi;tetr;chlo"

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

        json_file = tmp_path / "test_multi_barcode.amr.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        assert len(records) == 2
        assert records[0]['barcode'] == "barcode01"
        assert records[0]['pass_status'] == True
        assert records[1]['barcode'] == "barcode02"
        assert records[1]['pass_status'] == False

    @pytest.mark.unit
    def test_parse_empty_results(self, tmp_path):
        """Test parsing JSON with empty results."""
        test_data = {
            "barcode01": {
                "pass": True,
                "results": {}
            }
        }

        json_file = tmp_path / "test_empty.amr.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        assert len(records) == 0

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

        json_file = tmp_path / "test_no_resistance.amr.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)

        records = parse_amr_json_file(str(json_file), run_accession="RUN001")

        assert len(records) == 1
        assert records[0]['resistance'] is None
        # short_name becomes empty string when there are no valid resistance tokens
        assert records[0]['short_name'] == '' or records[0]['short_name'] is None
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
        summary = pd.read_csv(summary_file, index_col=0)
        assert len(summary) == 2  # Two unique resistance types
        assert 'ampicillin' in summary.index
        assert 'tetracycline' in summary.index

    @pytest.mark.unit
    def test_create_summary_no_output_dir(self):
        """Test creating summary without output directory."""
        df = pd.DataFrame({
            'resistance': ['ampicillin'],
            'run_accession': ['RUN001'],
            'barcode': ['barcode01'],
            'sequence': ['ATCG'],
            'coverage_percent': [95.0],
            'identity_percent': [99.0],
            'sample_id': ['SITE01_WW_001']
        })

        # Should not raise error when out_dir is None
        create_summary(df, None, None)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

