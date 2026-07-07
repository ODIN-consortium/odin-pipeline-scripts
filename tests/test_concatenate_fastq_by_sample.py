"""
Unit tests for concatenate_fastq_by_sample.py module.

Tests cover:
- Metadata info retrieval
- Directory finding
- File concatenation logic
- User prompt display (mocked)
"""

import pytest
import pandas as pd
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from concatenate_fastq_by_sample import (
    find_fastq_directories,
    concatenate_fastq_files_by_metadata,
)


class TestFindFastqDirectories:
    """Tests for find_fastq_directories function."""

    @pytest.mark.unit
    def test_find_single_directory(self, tmp_path):
        """Test finding fastq_pass directory for a single run."""
        # Create directory structure
        run_dir = tmp_path / "experiment" / "sample" / "RUN001"
        fastq_dir = run_dir / "fastq_pass"
        fastq_dir.mkdir(parents=True)

        result = find_fastq_directories(str(tmp_path), ["RUN001"])

        assert "RUN001" in result
        assert result["RUN001"] == fastq_dir

    @pytest.mark.unit
    def test_find_multiple_directories(self, tmp_path):
        """Test finding fastq_pass directories for multiple runs."""
        # Create directory structures
        run1_dir = tmp_path / "exp1" / "RUN001" / "fastq_pass"
        run1_dir.mkdir(parents=True)

        run2_dir = tmp_path / "exp2" / "RUN002" / "fastq_pass"
        run2_dir.mkdir(parents=True)

        result = find_fastq_directories(str(tmp_path), ["RUN001", "RUN002"])

        assert len(result) == 2
        assert "RUN001" in result
        assert "RUN002" in result

    @pytest.mark.unit
    def test_missing_fastq_pass(self, tmp_path):
        """Test when run directory exists but fastq_pass doesn't."""
        # Create run directory without fastq_pass
        run_dir = tmp_path / "experiment" / "RUN001"
        run_dir.mkdir(parents=True)

        result = find_fastq_directories(str(tmp_path), ["RUN001"])

        # Should not find the directory
        assert "RUN001" not in result or result.get("RUN001") is None

    @pytest.mark.unit
    def test_no_run_directory(self, tmp_path):
        """Test when run directory doesn't exist at all."""
        result = find_fastq_directories(str(tmp_path), ["RUN999"])

        assert "RUN999" not in result or result.get("RUN999") is None

    @pytest.mark.unit
    def test_nested_run_directory(self, tmp_path):
        """Test finding deeply nested run directory."""
        # Create deeply nested structure
        run_dir = tmp_path / "level1" / "level2" / "level3" / "RUN001"
        fastq_dir = run_dir / "fastq_pass"
        fastq_dir.mkdir(parents=True)

        result = find_fastq_directories(str(tmp_path), ["RUN001"])

        assert "RUN001" in result
        assert result["RUN001"] == fastq_dir


class TestConcatenateFastqFilesByMetadata:
    """Tests for concatenate_fastq_files_by_metadata function."""

    @pytest.mark.unit
    def test_concatenate_single_barcode_single_run(self, tmp_path):
        """Test concatenating files for a single barcode from one run."""
        # Create directory structure with FASTQ files
        run_dir = tmp_path / "runs" / "RUN001" / "fastq_pass" / "barcode01"
        run_dir.mkdir(parents=True)

        # Create test FASTQ files
        (run_dir / "file1.fastq.gz").write_bytes(b"FASTQ1")
        (run_dir / "file2.fastq.gz").write_bytes(b"FASTQ2")

        fastq_pass_dirs = {
            "RUN001": tmp_path / "runs" / "RUN001" / "fastq_pass"
        }

        barcode_metadata = {
            "barcode01": {
                "run_accessions": ["RUN001"],
                "sampleName": "SAMPLE001",
                "sample_id": "SITE01_WW_001",
                "sampling_date": "2025-01-15"
            }
        }

        output_dir = tmp_path / "output"

        output_files, identifier = concatenate_fastq_files_by_metadata(
            fastq_pass_dirs, barcode_metadata, str(output_dir)
        )

        assert len(output_files) == 1
        assert "barcode01" in output_files
        assert Path(output_files["barcode01"]).exists()
        assert identifier == "RUN001"

    @pytest.mark.unit
    def test_concatenate_multiple_barcodes(self, tmp_path):
        """Test concatenating files for multiple barcodes."""
        # Create directory structure
        fastq_dir = tmp_path / "runs" / "RUN001" / "fastq_pass"

        barcode01_dir = fastq_dir / "barcode01"
        barcode01_dir.mkdir(parents=True)
        (barcode01_dir / "file1.fastq.gz").write_bytes(b"FASTQ1")

        barcode02_dir = fastq_dir / "barcode02"
        barcode02_dir.mkdir(parents=True)
        (barcode02_dir / "file2.fastq.gz").write_bytes(b"FASTQ2")

        fastq_pass_dirs = {"RUN001": fastq_dir}

        barcode_metadata = {
            "barcode01": {
                "run_accessions": ["RUN001"],
                "sampleName": "SAMPLE001",
                "sample_id": "SITE01_WW_001",
                "sampling_date": "2025-01-15"
            },
            "barcode02": {
                "run_accessions": ["RUN001"],
                "sampleName": "SAMPLE002",
                "sample_id": "SITE01_WW_002",
                "sampling_date": "2025-01-15"
            }
        }

        output_dir = tmp_path / "output"

        output_files, identifier = concatenate_fastq_files_by_metadata(
            fastq_pass_dirs, barcode_metadata, str(output_dir)
        )

        assert len(output_files) == 2
        assert "barcode01" in output_files
        assert "barcode02" in output_files

    @pytest.mark.unit
    def test_concatenate_multiple_runs_merged(self, tmp_path):
        """Test concatenating files from multiple runs (merged scenario)."""
        # Create directory structures for two runs
        run1_dir = tmp_path / "runs" / "RUN001" / "fastq_pass" / "barcode01"
        run1_dir.mkdir(parents=True)
        (run1_dir / "file1.fastq.gz").write_bytes(b"FASTQ1")

        run2_dir = tmp_path / "runs" / "RUN002" / "fastq_pass" / "barcode01"
        run2_dir.mkdir(parents=True)
        (run2_dir / "file2.fastq.gz").write_bytes(b"FASTQ2")

        fastq_pass_dirs = {
            "RUN001": tmp_path / "runs" / "RUN001" / "fastq_pass",
            "RUN002": tmp_path / "runs" / "RUN002" / "fastq_pass"
        }

        barcode_metadata = {
            "barcode01": {
                "run_accessions": ["RUN001", "RUN002"],
                "sampleName": "SAMPLE001_MERGED",
                "sample_id": "SITE01_WW_001",
                "sampling_date": "2025-01-15"
            }
        }

        output_dir = tmp_path / "output"

        output_files, identifier = concatenate_fastq_files_by_metadata(
            fastq_pass_dirs, barcode_metadata, str(output_dir)
        )

        assert len(output_files) == 1
        assert "barcode01" in output_files
        # Identifier should be sampleName for merged runs
        assert identifier == "SAMPLE001_MERGED"

        # Verify concatenated file contains both files
        output_content = Path(output_files["barcode01"]).read_bytes()
        assert b"FASTQ1" in output_content
        assert b"FASTQ2" in output_content

    @pytest.mark.unit
    def test_concatenate_no_files_found(self, tmp_path):
        """Test when no FASTQ files are found for a barcode."""
        # Create directory structure but no files
        fastq_dir = tmp_path / "runs" / "RUN001" / "fastq_pass"
        barcode_dir = fastq_dir / "barcode01"
        barcode_dir.mkdir(parents=True)

        fastq_pass_dirs = {"RUN001": fastq_dir}

        barcode_metadata = {
            "barcode01": {
                "run_accessions": ["RUN001"],
                "sampleName": "SAMPLE001",
                "sample_id": "SITE01_WW_001",
                "sampling_date": "2025-01-15"
            }
        }

        output_dir = tmp_path / "output"

        output_files, identifier = concatenate_fastq_files_by_metadata(
            fastq_pass_dirs, barcode_metadata, str(output_dir)
        )

        # Should return empty dict when no files found
        assert len(output_files) == 0

    @pytest.mark.unit
    def test_concatenate_missing_run_directory(self, tmp_path):
        """Test when run directory is missing from fastq_pass_dirs."""
        fastq_pass_dirs = {}  # Empty - no directories found

        barcode_metadata = {
            "barcode01": {
                "run_accessions": ["RUN999"],
                "sampleName": "SAMPLE001",
                "sample_id": "SITE01_WW_001",
                "sampling_date": "2025-01-15"
            }
        }

        output_dir = tmp_path / "output"

        output_files, identifier = concatenate_fastq_files_by_metadata(
            fastq_pass_dirs, barcode_metadata, str(output_dir)
        )

        # Should handle missing directory gracefully
        assert len(output_files) == 0


class TestDisplayRunAccessionTableAndPrompt:
    """Tests for display_run_accession_table_and_prompt function."""

    @pytest.mark.unit
    @patch('builtins.input', return_value='1')
    def test_user_chooses_all_runs(self, mock_input):
        """Test when user chooses to use all runs."""
        from concatenate_fastq_by_sample import display_run_accession_table_and_prompt

        metadata_df = pd.DataFrame({
            'sampleName': ['SAMPLE001', 'SAMPLE001'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode01'],
            'run_accession': ['RUN001', 'RUN002']
        })

        result = display_run_accession_table_and_prompt(metadata_df, 'RUN001')

        assert result == True

    @pytest.mark.unit
    @patch('builtins.input', return_value='2')
    def test_user_chooses_single_run(self, mock_input):
        """Test when user chooses to use only the provided run."""
        from concatenate_fastq_by_sample import display_run_accession_table_and_prompt

        metadata_df = pd.DataFrame({
            'sampleName': ['SAMPLE001', 'SAMPLE001'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode01'],
            'run_accession': ['RUN001', 'RUN002']
        })

        result = display_run_accession_table_and_prompt(metadata_df, 'RUN001')

        assert result == False

    @pytest.mark.unit
    @patch('builtins.input', side_effect=['invalid', '3', '1'])
    def test_user_invalid_then_valid_choice(self, mock_input):
        """Test when user provides invalid choices before valid one."""
        from concatenate_fastq_by_sample import display_run_accession_table_and_prompt

        metadata_df = pd.DataFrame({
            'sampleName': ['SAMPLE001'],
            'sample_id': ['SITE01_WW_001'],
            'sampling_date': ['2025-01-15'],
            'barcode': ['barcode01'],
            'run_accession': ['RUN001']
        })

        result = display_run_accession_table_and_prompt(metadata_df, 'RUN001')

        # Should eventually accept valid choice '1'
        assert result == True


class TestGetMetadataInfo:
    """Tests for get_metadata_info function (requires mocking file I/O)."""

    @pytest.mark.unit
    @patch('concatenate_fastq_by_sample.read_nanopore_metadata')
    @patch('concatenate_fastq_by_sample.get_connected_run_accessions')
    @patch('builtins.input', return_value='2')
    def test_get_metadata_single_run(self, mock_input, mock_get_connected, mock_read_metadata):
        """Test getting metadata for a single run accession."""
        from concatenate_fastq_by_sample import get_metadata_info

        # Mock metadata
        mock_metadata = pd.DataFrame({
            'run_accession': ['RUN001'],
            'barcode': ['barcode01'],
            'sample_id': ['SITE01_WW_001'],
            'sampling_date': ['2025-01-15'],
            'sampleName': ['SAMPLE001']
        })
        mock_read_metadata.return_value = mock_metadata
        mock_get_connected.return_value = pd.DataFrame()  # No connected runs

        run_accessions, barcode_metadata = get_metadata_info(
            'metadata.xlsx', 'RUN001', 'run_accession'
        )

        assert len(run_accessions) == 1
        assert 'RUN001' in run_accessions
        assert 'barcode01' in barcode_metadata

    @pytest.mark.unit
    @patch('concatenate_fastq_by_sample.read_nanopore_metadata')
    def test_get_metadata_by_sample_id(self, mock_read_metadata):
        """Test getting metadata by sample_id."""
        from concatenate_fastq_by_sample import get_metadata_info

        # Mock metadata with multiple runs for same sample
        mock_metadata = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002'],
            'barcode': ['barcode01', 'barcode01'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15'],
            'sampleName': ['SAMPLE001', 'SAMPLE001']
        })
        mock_read_metadata.return_value = mock_metadata

        run_accessions, barcode_metadata = get_metadata_info(
            'metadata.xlsx', 'SITE01_WW_001', 'sample_id'
        )

        assert len(run_accessions) == 2
        assert 'RUN001' in run_accessions
        assert 'RUN002' in run_accessions


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

