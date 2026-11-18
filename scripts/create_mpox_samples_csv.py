import os
import sys
import csv
import pandas as pd
import warnings
import re
from nanopore_metadata import read_nanopore_metadata

# Suppress openpyxl warnings
warnings.filterwarnings("ignore", message="Data Validation extension is not supported and will be removed")


def validate_fastq_directory(input_dir: str):
    """
    Validate that the input directory contains barcode directories with fastq.gz files within
    """
    if not os.path.isdir(input_dir):
        return False

    # check if the input directory contains any subdirectories named barcodeXX
    barcode_dirs = [d for d in os.listdir(input_dir) if
                    os.path.isdir(os.path.join(input_dir, d)) and re.match(r'barcode\d{2}', d)]
    if not barcode_dirs:
        return False
    fastq_files = []
    for barcode_dir in barcode_dirs:
        barcode_path = os.path.join(input_dir, barcode_dir)
        fastq_files.append([f for f in os.listdir(barcode_path) if f.endswith('.fastq.gz')])
        if len(fastq_files) > 0:
            break
    return len(fastq_files) > 0


def main():
    if len(sys.argv) != 5:
        print("Usage: create_mpox_samples_csv.py <run_accession> <fastq_directory> <output_csv_file> <metadata_file>")
        sys.exit(1)

    run_accession = sys.argv[1]
    fastq_directory = sys.argv[2]
    output_csv_file = sys.argv[3]
    metadata_file = sys.argv[4]

    if not os.path.isfile(metadata_file):
        print(f"ERROR: Metadata file not found: {metadata_file}")
        sys.exit(1)

    if not validate_fastq_directory(fastq_directory):
        print(f"ERROR: The directory {fastq_directory} does not contain any barcode directories.")
        sys.exit(1)

    df = read_nanopore_metadata(metadata_file)
    # Filter by run_accession
    df = df.loc[df["run_accession"] == run_accession]
    if df.empty:
        print(f"ERROR: No metadata found for run_accession: {run_accession}")
        sys.exit(1)
    if 'type' not in df.columns:
        print(f"ERROR: 'type' column not found in metadata file. 'type' column is required for mpox pipeline.")
        sys.exit(1)

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_csv_file)
    os.makedirs(output_dir, exist_ok=True)

    barcode_dirs = [d for d in os.listdir(fastq_directory) if
                    os.path.isdir(os.path.join(fastq_directory, d)) and re.match(r'barcode\d*', d)]

    allowed_types = ['test_sample', 'positive_control', 'negative_control', 'no_template_control']

    # Track files that were skipped
    processed_files = []
    skipped_files = []
    # Create the CSV file and add header
    with open(output_csv_file, mode='w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["barcode", "alias", "type"])

        # Process the barcode dirs and generate CSV content
        for barcode in barcode_dirs:
            barcode_df = df.loc[df['barcode'] == barcode]
            if barcode_df.empty:
                skipped_files.append(barcode)
                continue
            sample_type = barcode_df['type'].values[0]
            sample_type = str(sample_type).strip().lower()
            if sample_type in ('nan', 'none', ''):
                raise ValueError(
                    f"ERROR: 'type' column is blank for barcode '{barcode}' "
                    f"(run_accession={run_accession}) in the nanopore metadata sheet. "
                    f"Fill it in with one of: {', '.join(allowed_types)}")
            if sample_type not in allowed_types:
                raise ValueError(
                    f"ERROR: Invalid sample type '{sample_type}' for barcode '{barcode}' "
                    f"(run_accession={run_accession}). Allowed types are: {', '.join(allowed_types)}")
            alias = barcode_df['alias'].values[0]
            alias = str(alias).strip()
            if not alias or len(alias) == 0 or alias.lower() == 'nan':
                # If alias is missing, create one using barcode and sample_code
                alias = barcode + '_' + barcode_df['sample_code'].values[0]
            processed_files.append(barcode)
            # Write row to CSV
            csv_writer.writerow([barcode, alias, sample_type])

    # Report on the processing
    print(f"\nSample CSV file created at: {output_csv_file}")
    print(f"Number of samples included: {len(processed_files)}")

    # Report any files that were skipped
    if skipped_files:
        print(
            f"INFO: {len(skipped_files)} barcode directories were skipped as their barcodes were not found in the metadata. Skipped barcodes: {', '.join(skipped_files)}")


if __name__ == "__main__":
    main()
