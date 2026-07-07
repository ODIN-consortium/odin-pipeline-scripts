"""
Unit tests for create_kraken_datasets.py module.

Tests cover:
- Kraken2 report to DataFrame conversion
- Dataset creation from metadata
- File discovery and processing
"""

import pytest
import pandas as pd
import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from create_kraken_datasets import (
    kraken2_to_dataframe,
    reclassify_salmonella,
)


class TestKraken2ToDataframe:
    """Tests for kraken2_to_dataframe function."""

    @pytest.mark.unit
    def test_kraken2_basic_conversion(self, tmp_path):
        """Test basic conversion of Kraken2 report to DataFrame."""
        # Create a minimal Kraken2 report file
        kraken_report = tmp_path / "test.kreport"
        kraken_report.write_text(
            "100.00\t1000\t1000\tU\t0\tunclassified\n"
            "50.00\t500\t100\tD\t1\tBacteria\n"
            "25.00\t250\t50\tP\t2\tProteobacteria\n"
        )

        # Use the column names that kraken_parser expects
        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        df = kraken2_to_dataframe(str(kraken_report), column_names)

        assert len(df) > 0
        assert 'Pct. of Frags' in df.columns
        assert 'Scientific name' in df.columns

    @pytest.mark.unit
    def test_kraken2_empty_file(self, tmp_path):
        """Test handling of empty Kraken2 report file."""
        kraken_report = tmp_path / "empty.kreport"
        kraken_report.write_text("")

        column_names = ['percentage', 'clade_fragments', 'taxon_fragments',
                       'rank_code', 'ncbi_taxid', 'scientific_name']

        df = kraken2_to_dataframe(str(kraken_report), column_names)

        # Should return empty DataFrame
        assert len(df) == 0

    @pytest.mark.unit
    def test_kraken2_with_enrichment(self, tmp_path):
        """Test that lineage enrichment is applied."""
        kraken_report = tmp_path / "enriched.kreport"
        kraken_report.write_text(
            "100.00\t1000\t1000\tU\t0\tunclassified\n"
            "50.00\t500\t100\tD\t2\tBacteria\n"
            "25.00\t250\t50\tP\t1224\tProteobacteria\n"
            "12.50\t125\t25\tC\t1236\tGammaproteobacteria\n"
        )

        # Use the column names that kraken_parser expects
        column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags',
                       'Rank code', 'NCBI tax ID', 'Scientific name']

        df = kraken2_to_dataframe(str(kraken_report), column_names)

        # Check that lineage enrichment columns are added
        assert any('domain' in col.lower() or 'phylum' in col.lower() or 'class' in col.lower()
                  for col in df.columns)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


def _make_salmonella_df():
    """Minimal DataFrame mimicking output of add_pathogens() for Salmonella rows.

    With the new two-tier display design, add_pathogens() assigns all S. enterica
    TaxIDs (28901, 90370, 90371) to 'Salmonella enterica' via lineage matching.
    reclassify_salmonella() then separates out 90370 (Typhi) and 90371 (Typhimurium).
    """
    return pd.DataFrame({
        'file_name':                ['rep.kreport2'] * 3,
        'NCBI tax ID':              ['28901', '90370', '90371'],
        'Scientific name':          [
            'Salmonella enterica',
            'Salmonella enterica subsp. enterica serovar Typhi',
            'Salmonella enterica subsp. enterica serovar Typhimurium',
        ],
        'No of Frags root':         [108713, 3, 108662],
        'No of Frags':              [11, 3, 96282],
        'Priority pathogen group':  [
            'Salmonella enterica',   # add_pathogens() label for 28901
            'Salmonella enterica',   # 90370 labelled by lineage match before reclassify
            'Salmonella enterica',   # 90371 labelled by lineage match before reclassify
        ],
    })


class TestReclassifySalmonella:
    """Tests for reclassify_salmonella() — TaxID-based reassignment."""

    @pytest.mark.unit
    def test_typhi_reclassified_by_taxid(self):
        df = _make_salmonella_df()
        result = reclassify_salmonella(df)
        assert result[result['NCBI tax ID'] == '90370']['Priority pathogen group'].iloc[0] == 'Salmonella Typhi'

    @pytest.mark.unit
    def test_typhimurium_kept_distinct_from_enterica(self):
        """TaxID 90371 is relabelled to prevent double-counting with 28901 clade total."""
        df = _make_salmonella_df()
        result = reclassify_salmonella(df)
        assert result[result['NCBI tax ID'] == '90371']['Priority pathogen group'].iloc[0] == 'Salmonella Typhimurium'

    @pytest.mark.unit
    def test_enterica_anchor_unchanged(self):
        """TaxID 28901 (S. enterica) should remain 'Salmonella enterica' (shown under AMR)."""
        df = _make_salmonella_df()
        result = reclassify_salmonella(df)
        assert result[result['NCBI tax ID'] == '28901']['Priority pathogen group'].iloc[0] == 'Salmonella enterica'

    @pytest.mark.unit
    def test_non_salmonella_rows_unchanged(self):
        df = pd.DataFrame({
            'NCBI tax ID': ['562'],
            'Priority pathogen group': ['ESBL/Carbapenemase producing E. coli\u200b'],
        })
        result = reclassify_salmonella(df)
        assert result['Priority pathogen group'].iloc[0] == 'ESBL/Carbapenemase producing E. coli\u200b'


