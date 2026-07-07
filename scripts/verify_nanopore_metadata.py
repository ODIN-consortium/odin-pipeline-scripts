import os
import sys
import warnings
from glob import glob
import logging
import pandas as pd
from datetime import datetime
from nanopore_metadata import read_nanopore_metadata, extract_site_and_type_from_sample_id

# Suppress openpyxl Data Validation warning
warnings.filterwarnings("ignore", message="Data Validation extension is not supported and will be removed")
logger = logging.getLogger(__name__)


def error_exit(message):
    """Print an error message with ERROR: prefix and exit with code 1"""
    print(f"ERROR: {message}", file=sys.stdout)
    sys.exit(1)


def main():
    # Check if we have the correct number of arguments
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("\nUsage: python verify_nanopore_metadata.py <minknow_data_folder> <metadata.xlsx> [run_accession]")
        print("\nIf run_accession is provided, only that specific run will be verified.")
        print("If omitted, all runs in the metadata file will be verified.")
        sys.exit(1)

    minknow_data_folder = sys.argv[1]
    xlsx_path = sys.argv[2]
    # Get the optional run_accession if provided
    specific_run_accession = sys.argv[3] if len(sys.argv) == 4 else None

    if not os.path.isfile(xlsx_path):
        error_exit(f"Metadata file not found: {xlsx_path}")

    print(f"\nVerifying metadata file {xlsx_path} for Nanopore sequencing data...")
    if specific_run_accession:
        print(f"Verifying run_accession: {specific_run_accession}")

    # Read column names from line 2 (header=1), data starts at line 4 (skiprows=3)
    df = read_nanopore_metadata(xlsx_path)

    # If a specific run_accession was provided, filter the DataFrame
    if specific_run_accession:
        df = df.loc[df["run_accession"] == specific_run_accession]
        if df.empty:
            error_exit(f"No metadata found for run_accession: {specific_run_accession}")

    # Skip rows with missing barcode values (NaN or empty string)
    df = df.loc[df["barcode"].notna() & (df["barcode"].str.strip() != "")]
    if df.empty:
        if specific_run_accession:
            error_exit(f"No barcode values found for run_accession: {specific_run_accession}")
        else:
            error_exit(f"No barcode values found in the metadata file.")

    # verify that there are no duplicates of run_accession and barcode
    duplicates = df.loc[df.duplicated(subset=["run_accession", "barcode"], keep=False)]
    if not duplicates.empty:
        error_exit(f"Duplicate entries found for run_accession and barcode:\n{duplicates[['run_accession', 'barcode']]}")

    required_cols = ["sampling_date", "barcode", "sample_id", "run_accession"]
    for col in required_cols:
        if col not in df.columns:
            error_exit(f"Missing column: {col}")

    for idx, row in df.iterrows():
        # Validate sampling_date format
        sampling_date = str(row["sampling_date"])
        try:
            datetime.strptime(sampling_date, "%Y%m%d")
        except (ValueError, TypeError):
            error_exit(
                f"Invalid sampling_date format for sample_id:{row['sample_id']}: '{sampling_date}' (expected format YYYYMMDD)")
        # Validate that the columns are not empty
        for col in required_cols:
            if pd.isna(row[col]) or str(row[col]).strip() == "":
                error_exit(f"Missing value in column '{col}' for sample_id: {row['sample_id']}")
        # Validate sample_id format for extracting sampling_site_id and sample_type
        sampling_site_id, sample_type = extract_site_and_type_from_sample_id(row["sample_id"])
        if not sampling_site_id or not sample_type:
            error_exit(f"Invalid sample_id format for extracting sampling_site_id and sample_type: {row['sample_id']}")
    print("All entries verified successfully.")


if __name__ == '__main__':
    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)],
                        format='%(asctime)s loglevel=%(levelname)-6s path=%(filename)s %(funcName)s() '
                               'L%(lineno)-4d message=%(message)s',
                        encoding='utf-8', level='INFO')
    main()
