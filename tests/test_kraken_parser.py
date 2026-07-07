"""
Unit tests for kraken_parser.py module.

Tests cover:
- Reading Kraken2 reports
- Enriching lineage information
- Handling various taxonomic ranks
"""

import pytest
import pandas as pd
import sys
import os
from io import StringIO

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from kraken_parser import (
    read_kraken2_report,
    enrich_kraken2_lineage,
    RANK_COLUMN_MAPPING,
)


class TestReadKraken2Report:
    """Tests for read_kraken2_report function."""

    @pytest.mark.unit
    def test_read_basic_report(self, tmp_path):
        """Test reading a basic Kraken2 report file."""
        report = tmp_path / "test.kreport"
        report.write_text(
            "100.00\t1000\t1000\tU\t0\tunclassified\n"
            "50.00\t500\t100\tD\t2\tBacteria\n"
        )

        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        df = read_kraken2_report(str(report), column_names)

        assert len(df) == 2
        assert df.iloc[0]['Scientific name'] == 'unclassified'
        assert df.iloc[1]['Scientific name'] == 'Bacteria'

    @pytest.mark.unit
    def test_strip_whitespace(self, tmp_path):
        """Test that leading/trailing whitespace is stripped."""
        report = tmp_path / "whitespace.kreport"
        report.write_text(
            "100.00\t1000\t1000\tU\t0\t  unclassified  \n"
            "50.00\t500\t100\tD\t2\t  Bacteria  \n"
        )

        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        df = read_kraken2_report(str(report), column_names)

        assert df.iloc[0]['Scientific name'] == 'unclassified'
        assert df.iloc[1]['Scientific name'] == 'Bacteria'

    @pytest.mark.unit
    def test_read_empty_report(self, tmp_path):
        """Test reading an empty report file."""
        report = tmp_path / "empty.kreport"
        report.write_text("")

        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        df = read_kraken2_report(str(report), column_names)

        assert len(df) == 0


class TestEnrichKraken2Lineage:
    """Tests for enrich_kraken2_lineage function."""

    @pytest.mark.unit
    def test_enrich_simple_lineage(self):
        """Test enriching a simple lineage with Domain and Phylum."""
        df = pd.DataFrame({
            'Rank code': ['D', 'P'],
            'Scientific name': ['Bacteria', 'Proteobacteria']
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        assert 'Domain' in result.columns
        assert 'Phylum' in result.columns
        assert result.iloc[0]['Domain'] == 'Bacteria'
        assert result.iloc[1]['Domain'] == 'Bacteria'
        assert result.iloc[1]['Phylum'] == 'Proteobacteria'

    @pytest.mark.unit
    def test_enrich_full_lineage(self):
        """Test enriching a full taxonomic lineage."""
        df = pd.DataFrame({
            'Rank code': ['D', 'P', 'C', 'O', 'F', 'G', 'S'],
            'Scientific name': [
                'Bacteria',
                'Proteobacteria',
                'Gammaproteobacteria',
                'Vibrionales',
                'Vibrionaceae',
                'Vibrio',
                'Vibrio cholerae'
            ]
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # Check that all ranks are populated for the species row
        species_row = result.iloc[-1]
        assert species_row['Domain'] == 'Bacteria'
        assert species_row['Phylum'] == 'Proteobacteria'
        assert species_row['Class'] == 'Gammaproteobacteria'
        assert species_row['Order'] == 'Vibrionales'
        assert species_row['Family'] == 'Vibrionaceae'
        assert species_row['Genus'] == 'Vibrio'
        assert species_row['Species'] == 'Vibrio cholerae'

    @pytest.mark.unit
    def test_enrich_clears_lower_levels(self):
        """Test that lower taxonomic levels are cleared when moving to a higher level."""
        df = pd.DataFrame({
            'Rank code': ['D', 'P', 'C', 'P'],
            'Scientific name': [
                'Bacteria',
                'Proteobacteria',
                'Gammaproteobacteria',
                'Firmicutes'  # New phylum should clear previous class
            ]
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # The last row should have Firmicutes as Phylum but empty Class
        last_row = result.iloc[-1]
        assert last_row['Phylum'] == 'Firmicutes'
        assert last_row['Class'] == ''

    @pytest.mark.unit
    def test_enrich_with_unclassified(self):
        """Test enriching lineage with unclassified entries."""
        df = pd.DataFrame({
            'Rank code': ['U', 'D', 'P'],
            'Scientific name': ['unclassified', 'Bacteria', 'Proteobacteria']
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # Unclassified should be skipped but not cause errors
        assert len(result) == 3
        assert result.iloc[1]['Domain'] == 'Bacteria'

    @pytest.mark.unit
    def test_enrich_with_intermediate_ranks(self):
        """Test enriching lineage with intermediate ranks like F1, P1."""
        df = pd.DataFrame({
            'Rank code': ['D', 'P', 'P1', 'C'],
            'Scientific name': [
                'Bacteria',
                'Proteobacteria',
                'Pseudomonadota',  # P1 - intermediate rank
                'Gammaproteobacteria'
            ]
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # P1 should be treated as Phylum-level (base rank 'P')
        # The Class row should have Phylum set from the actual P rank
        class_row = result.iloc[-1]
        assert class_row['Domain'] == 'Bacteria'
        assert class_row['Class'] == 'Gammaproteobacteria'

    @pytest.mark.unit
    def test_enrich_empty_dataframe(self):
        """Test enriching an empty DataFrame."""
        df = pd.DataFrame({
            'Rank code': [],
            'Scientific name': []
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # Should add columns but have no rows
        assert len(result) == 0
        assert 'Domain' in result.columns
        assert 'Phylum' in result.columns

    @pytest.mark.unit
    def test_enrich_maintains_lineage_across_branches(self):
        """Test that lineage is properly maintained when switching between branches."""
        df = pd.DataFrame({
            'Rank code': ['D', 'P', 'C', 'P', 'C'],
            'Scientific name': [
                'Bacteria',
                'Proteobacteria',
                'Alphaproteobacteria',
                'Firmicutes',  # Switch to different phylum
                'Bacilli'  # Different class
            ]
        })

        result = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # Check first branch
        row_2 = result.iloc[2]
        assert row_2['Phylum'] == 'Proteobacteria'
        assert row_2['Class'] == 'Alphaproteobacteria'

        # Check second branch
        row_4 = result.iloc[4]
        assert row_4['Phylum'] == 'Firmicutes'
        assert row_4['Class'] == 'Bacilli'

    @pytest.mark.unit
    def test_rank_column_mapping_completeness(self):
        """Test that RANK_COLUMN_MAPPING contains expected ranks."""
        expected_ranks = ['R', 'D', 'K', 'P', 'C', 'O', 'F', 'G', 'S']
        for rank in expected_ranks:
            assert rank in RANK_COLUMN_MAPPING
            assert isinstance(RANK_COLUMN_MAPPING[rank], str)


class TestKrakenParserIntegration:
    """Integration tests combining read and enrich functions."""

    @pytest.mark.integration
    def test_read_and_enrich_workflow(self, tmp_path):
        """Test the full workflow of reading and enriching a Kraken2 report."""
        report = tmp_path / "full_workflow.kreport"
        report.write_text(
            "66.67\t8\t8\tU\t0\tunclassified\n"
            "33.33\t4\t0\tD\t2\tBacteria\n"
            "16.67\t2\t0\tP\t1224\tProteobacteria\n"
            "8.33\t1\t0\tC\t1236\tGammaproteobacteria\n"
            "8.33\t1\t1\tS\t666\tVibrio cholerae\n"
        )

        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        # Read the report
        df = read_kraken2_report(str(report), column_names)
        assert len(df) == 5

        # Enrich the lineage
        enriched = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

        # Verify enrichment worked
        species_row = enriched[enriched['Scientific name'] == 'Vibrio cholerae'].iloc[0]
        assert species_row['Domain'] == 'Bacteria'
        assert species_row['Phylum'] == 'Proteobacteria'
        assert species_row['Class'] == 'Gammaproteobacteria'
        assert species_row['Species'] == 'Vibrio cholerae'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

