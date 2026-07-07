"""
Unit tests for nanopore_metadata.py module.

Tests cover:
- Column dtype setting
- Site and type extraction from sample_id
- Metadata reading and validation
- Connected run accession finding
- Merge operations
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from nanopore_metadata import (
    set_column_dtypes,
    extract_site_and_type_from_sample_id,
    ensure_columns,
    get_connected_run_accessions,
)


class TestSetColumnDtypes:
    """Tests for set_column_dtypes function."""

    @pytest.mark.unit
    def test_convert_single_column(self):
        """Test converting a single column to a different dtype."""
        df = pd.DataFrame({'a': ['1', '2', '3'], 'b': ['4', '5', '6']})
        result = set_column_dtypes(df, {'a': 'int64'})
        assert result['a'].dtype == np.int64
        assert result['b'].dtype == object

    @pytest.mark.unit
    def test_convert_multiple_columns(self):
        """Test converting multiple columns at once."""
        df = pd.DataFrame({'a': ['1', '2', '3'], 'b': ['4.5', '5.5', '6.5'], 'c': ['7', '8', '9']})
        result = set_column_dtypes(df, {'a': 'int64', 'b': 'float64'})
        assert result['a'].dtype == np.int64
        assert result['b'].dtype == np.float64
        assert result['c'].dtype == object

    @pytest.mark.unit
    def test_nonexistent_column(self):
        """Test attempting to convert a column that doesn't exist."""
        df = pd.DataFrame({'a': ['1', '2', '3']})
        result = set_column_dtypes(df, {'nonexistent': 'int64'})
        # Should not raise error, just log warning
        assert 'a' in result.columns
        assert 'nonexistent' not in result.columns

    @pytest.mark.unit
    def test_invalid_conversion(self):
        """Test attempting an invalid type conversion."""
        df = pd.DataFrame({'a': ['abc', 'def', 'ghi']})
        result = set_column_dtypes(df, {'a': 'int64'})
        # Should log warning and keep original dtype
        assert result['a'].dtype == object

    @pytest.mark.unit
    def test_empty_dataframe(self):
        """Test converting dtypes on an empty DataFrame."""
        df = pd.DataFrame()
        result = set_column_dtypes(df, {'a': 'int64'})
        assert len(result) == 0


class TestExtractSiteAndTypeFromSampleId:
    """Tests for extract_site_and_type_from_sample_id function."""

    @pytest.mark.unit
    def test_valid_sample_id_with_suffix(self):
        """Test extracting from a valid sample_id with additional suffix."""
        site, sample_type = extract_site_and_type_from_sample_id('SITE01_WW_001')
        assert site == 'SITE01'
        assert sample_type == 'WW'

    @pytest.mark.unit
    def test_valid_sample_id_without_suffix(self):
        """Test extracting from a valid sample_id without suffix."""
        site, sample_type = extract_site_and_type_from_sample_id('SITE02_TP')
        assert site == 'SITE02'
        assert sample_type == 'TP'

    @pytest.mark.unit
    def test_invalid_sample_id_single_part(self):
        """Test with invalid sample_id containing only one part."""
        site, sample_type = extract_site_and_type_from_sample_id('SITE01')
        assert site is None
        assert sample_type is None

    @pytest.mark.unit
    def test_invalid_sample_id_empty(self):
        """Test with empty sample_id."""
        site, sample_type = extract_site_and_type_from_sample_id('')
        assert site is None
        assert sample_type is None

    @pytest.mark.unit
    def test_sample_id_with_many_parts(self):
        """Test sample_id with many underscore-separated parts."""
        site, sample_type = extract_site_and_type_from_sample_id('SITE03_WW_2023_01_15')
        assert site == 'SITE03'
        assert sample_type == 'WW'


class TestEnsureColumns:
    """Tests for ensure_columns function."""

    @pytest.mark.unit
    def test_all_columns_present(self):
        """Test when all required columns are present."""
        df = pd.DataFrame({'a': [1, 2], 'b': [3, 4], 'c': [5, 6]})
        result = ensure_columns(df, ['a', 'b'])
        assert 'a' in result.columns
        assert 'b' in result.columns

    @pytest.mark.unit
    def test_missing_columns_raises_error(self):
        """Test that missing columns raise a ValueError."""
        df = pd.DataFrame({'a': [1, 2]})
        with pytest.raises(ValueError, match='Missing columns in dataframe'):
            ensure_columns(df, ['a', 'b', 'c'])

    @pytest.mark.unit
    def test_empty_required_list(self):
        """Test with empty required columns list."""
        df = pd.DataFrame({'a': [1, 2]})
        result = ensure_columns(df, [])
        assert result.equals(df)


class TestGetConnectedRunAccessions:
    """Tests for get_connected_run_accessions function."""

    @pytest.mark.unit
    def test_single_run_no_connections(self):
        """Test when a run has no connected runs."""
        metadata_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002'],
            'sample_id': ['SITE01_WW_001', 'SITE02_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode01']
        })
        result = get_connected_run_accessions(metadata_df, 'RUN001')
        assert result.empty

    @pytest.mark.unit
    def test_multiple_connected_runs_same_sample(self):
        """Test when multiple runs share sample_id, date, and barcode."""
        metadata_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002', 'RUN003'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001', 'SITE02_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode01', 'barcode01']
        })
        result = get_connected_run_accessions(metadata_df, 'RUN001')
        assert len(result) == 2
        assert 'RUN001' in result['run_accession'].values
        assert 'RUN002' in result['run_accession'].values
        assert 'RUN003' not in result['run_accession'].values

    @pytest.mark.unit
    def test_different_barcodes_not_connected(self):
        """Test that runs with different barcodes are not connected."""
        metadata_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN001'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode02']
        })
        result = get_connected_run_accessions(metadata_df, 'RUN001')
        assert result.empty

    @pytest.mark.unit
    def test_different_dates_not_connected(self):
        """Test that runs with different sampling_dates are not connected."""
        metadata_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-16'],
            'barcode': ['barcode01', 'barcode01']
        })
        result = get_connected_run_accessions(metadata_df, 'RUN001')
        assert result.empty

    @pytest.mark.unit
    def test_multiple_barcodes_same_sample(self):
        """Test with multiple barcodes for the same sample."""
        metadata_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002', 'RUN001', 'RUN002'],
            'sample_id': ['SITE01_WW_001', 'SITE01_WW_001', 'SITE01_WW_001', 'SITE01_WW_001'],
            'sampling_date': ['2025-01-15', '2025-01-15', '2025-01-15', '2025-01-15'],
            'barcode': ['barcode01', 'barcode01', 'barcode02', 'barcode02']
        })
        result = get_connected_run_accessions(metadata_df, 'RUN001')
        assert len(result) == 4
        assert set(result['barcode'].unique()) == {'barcode01', 'barcode02'}


class TestMergeWithExistingFile:
    """Tests for merge_with_existing_file function."""

    @pytest.mark.unit
    def test_no_existing_file(self, tmp_path):
        """Test when no existing file exists."""
        from nanopore_metadata import merge_with_existing_file

        new_df = pd.DataFrame({
            'run_accession': ['RUN001'],
            'data': ['value1']
        })

        nonexistent_file = tmp_path / "nonexistent.feather"
        result = merge_with_existing_file(new_df, {'RUN001'}, str(nonexistent_file))

        assert result.equals(new_df)

    @pytest.mark.unit
    def test_merge_with_existing_removes_duplicates(self, tmp_path):
        """Test that merging removes duplicates from existing file."""
        from nanopore_metadata import merge_with_existing_file

        # Create existing file
        existing_df = pd.DataFrame({
            'run_accession': ['RUN001', 'RUN002'],
            'data': ['old_value1', 'value2']
        })
        existing_file = tmp_path / "existing.feather"
        existing_df.to_feather(str(existing_file))

        # Create new data for RUN001
        new_df = pd.DataFrame({
            'run_accession': ['RUN001'],
            'data': ['new_value1']
        })

        result = merge_with_existing_file(new_df, {'RUN001'}, str(existing_file))

        # Should have 2 rows: new RUN001 and existing RUN002
        assert len(result) == 2
        assert 'RUN002' in result['run_accession'].values
        run001_data = result[result['run_accession'] == 'RUN001']['data'].iloc[0]
        assert run001_data == 'new_value1'


class TestWarnList:
    """Tests for warn_list function."""

    @pytest.mark.unit
    def test_empty_list_no_warning(self, caplog):
        """Test that empty list does not produce warning."""
        from nanopore_metadata import warn_list
        import logging

        with caplog.at_level(logging.WARNING):
            warn_list("Test message:", set())

        assert len(caplog.records) == 0

    @pytest.mark.unit
    def test_nonempty_list_produces_warning(self, caplog):
        """Test that non-empty list produces warning."""
        from nanopore_metadata import warn_list
        import logging

        with caplog.at_level(logging.WARNING):
            warn_list("Missing items:", {'item1', 'item2'})

        assert len(caplog.records) > 0
        assert 'Missing items:' in caplog.text


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

