"""
Shared test fixtures and configuration for all tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmp_dir = tempfile.mkdtemp()
    yield Path(tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def sample_metadata_dict():
    """Return sample metadata dictionary for testing."""
    return {
        'run_accession': ['RUN001', 'RUN002', 'RUN003'],
        'barcode': ['barcode01', 'barcode01', 'barcode02'],
        'sample_id': ['SITE01_WW_001', 'SITE01_WW_001', 'SITE02_TP_001'],
        'sampling_date': ['2025-01-15', '2025-01-15', '2025-01-16'],
        'sampleName': ['SAMPLE001', 'SAMPLE001', 'SAMPLE002'],
        'protocol_id': ['PROTO1', 'PROTO1', 'PROTO2'],
        'sequencing_kit_id': ['KIT1', 'KIT1', 'KIT2'],
    }


@pytest.fixture
def sample_sites_dict():
    """Return sample sites dictionary for testing."""
    return {
        'site_ID': ['SITE01', 'SITE02', 'SITE03'],
        'country': ['USA', 'Canada', 'Mexico'],
        'longitude': [-122.4194, -79.3832, -99.1332],
        'latitude': [37.7749, 43.6532, 19.4326],
    }


@pytest.fixture
def sample_amr_json():
    """Return sample AMR JSON structure for testing."""
    return {
        "barcode01": {
            "pass": True,
            "results": {
                "gene1": {
                    "count": 5,
                    "meta": [
                        {
                            "RESISTANCE": "ampicillin;tetracycline",
                            "SEQUENCE": "ATCGATCGATCG",
                            "START": 100,
                            "END": 500,
                            "%COVERAGE": 95.5,
                            "%IDENTITY": 99.2
                        }
                    ]
                },
                "gene2": {
                    "count": 3,
                    "meta": [
                        {
                            "RESISTANCE": "chloramphenicol",
                            "SEQUENCE": "GCTAGCTAGCTA",
                            "START": 200,
                            "END": 600,
                            "%COVERAGE": 92.0,
                            "%IDENTITY": 98.5
                        }
                    ]
                }
            }
        },
        "barcode02": {
            "pass": False,
            "results": {}
        }
    }


@pytest.fixture
def sample_kraken_report():
    """Return sample Kraken2 report content for testing."""
    return """66.67\t8\t8\tU\t0\tunclassified
33.33\t4\t0\tR\t1\troot
33.33\t4\t0\tD\t2\tBacteria
16.67\t2\t0\tP\t1224\tProteobacteria
8.33\t1\t0\tC\t1236\tGammaproteobacteria
8.33\t1\t0\tO\t135623\tVibrionales
8.33\t1\t0\tF\t641\tVibrionaceae
8.33\t1\t0\tG\t662\tVibrio
8.33\t1\t1\tS\t666\tVibrio cholerae
"""


@pytest.fixture
def kraken_column_names():
    """Return standard Kraken2 column names."""
    return [
        'Pct. of Frags',
        'No of Frags root',
        'No of Frags',
        'Rank code',
        'NCBI tax ID',
        'Scientific name'
    ]

