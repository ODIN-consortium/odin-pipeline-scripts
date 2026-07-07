import argparse
import csv
import glob
import os
import sys
import warnings

import pandas as pd

# Suppress openpyxl warnings
warnings.filterwarnings("ignore", message="Data Validation extension is not supported and will be removed")


def validate_input_seqs_dir(input_dir):
    """
    Validate that the input directory contains concatenated fastq.gz files
    """
    if not os.path.isdir(input_dir):
        return False

    # Check if there are any fastq.gz files in the directory or subdirectories
    fastq_files = glob.glob(os.path.join(input_dir, "**", "*.fastq.gz"), recursive=True)
    return len(fastq_files) > 0


def get_barcodes_from_metadata(metadata_file, identifier, identifier_type):
    """
    Extract barcode values for a specific run_accession or sample_id from the metadata file

    Args:
        metadata_file (str): Path to the metadata Excel file
        identifier (str): The run_accession or sample_id to filter by
        identifier_type (str): Either 'run_accession' or 'sample_id'

    Returns:
        list: List of barcode values for the specified run_accession
    """
    try:
        # Try to use existing read_nanopore_metadata function if available
        try:
            from nanopore_metadata import read_nanopore_metadata
            df = read_nanopore_metadata(metadata_file)
        except ImportError:
            # Read column names from line 2 (header=1), data starts at line 4 (skiprows=3)
            df = pd.read_excel(metadata_file, header=1, skiprows=2)

        # Filter by the specified identifier
        df = df.loc[df[identifier_type] == identifier]
        if df.empty:
            print(f"ERROR: No metadata found for {identifier_type}: {identifier}")
            sys.exit(1)
        # verify that all dates for one barcode value are the same
        for barcode, group in df.groupby("barcode"):
            unique_dates = group["sampling_date"].dropna().unique()
            if len(unique_dates) > 1:
                print(
                    f"ERROR: Multiple sampling_date values found for barcode '{barcode}' under {identifier_type} '{identifier}': {unique_dates.tolist()}")
                print(f"ERROR: All entries for the same barcode must have the same sampling_date")
                sys.exit(1)

        # Filter out rows with missing barcode values
        df = df.loc[df["barcode"].notna() & (df["barcode"].str.strip() != "")]
        if df.empty:
            print(f"ERROR: No barcode values found for {identifier_type}: {identifier}")
            sys.exit(1)

        # Return the list of barcodes
        return df["barcode"].unique().tolist()

    except Exception as e:
        print(f"ERROR: Failed to read metadata file: {e}")
        sys.exit(1)


# ANSI color codes for alert messages
INFO_COLOR = '\033[1;93m'  # Bright yellow
WARNING_COLOR = '\033[91m'  # Red
RESET_COLOR = '\033[0m'


def print_info(msg):
    print(f"{INFO_COLOR}INFO: {msg}{RESET_COLOR}", file=sys.stderr)


def print_warning(msg):
    print(f"{WARNING_COLOR}WARNING: {msg}{RESET_COLOR}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Create CSV file for samples based on run_accession or sample_id')

    # Create mutually exclusive group for run_accession and sample_id
    identifier_group = parser.add_mutually_exclusive_group(required=True)
    identifier_group.add_argument('--run_accession', type=str, help='Run accession to filter by')
    identifier_group.add_argument('--sample_id', type=str, help='Sample ID to filter by')

    parser.add_argument('--input_seqs_directory', help='Directory containing fastq.gz files')
    parser.add_argument('--output_csv_file', help='Output CSV file path')
    parser.add_argument('--metadata_file', help='Metadata Excel file path')

    args = parser.parse_args()

    # Determine identifier type and value based on which argument was provided
    if args.run_accession:
        identifier_type = 'run_accession'
        identifier = args.run_accession
    else:  # args.sample_id
        identifier_type = 'sample_id'
        identifier = args.sample_id

    if not os.path.isfile(args.metadata_file):
        print(f"ERROR: Metadata file not found: {args.metadata_file}")
        sys.exit(1)

    if not validate_input_seqs_dir(args.input_seqs_directory):
        print(f"ERROR: The directory {args.input_seqs_directory} does not contain any fastq.gz files.")
        sys.exit(1)

    # Get barcodes from metadata
    valid_barcodes = get_barcodes_from_metadata(args.metadata_file, identifier, identifier_type)
    print_info(
        f"Found {len(valid_barcodes)} barcodes specified in metadata for {identifier_type} {identifier} : {', '.join(valid_barcodes)}")

    # Ensure the output directory exists
    output_dir = os.path.dirname(args.output_csv_file)
    os.makedirs(output_dir, exist_ok=True)

    # Create the CSV file and add header - use the identifier_type for the column name
    with open(args.output_csv_file, mode='w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        # nextflow requires sample and run_accession columns
        csv_writer.writerow(["sample", "run_accession", "instrument_platform", "fastq_1"])

        # Track files that were processed and skipped
        processed_files = []
        skipped_files = []

        # Process the concatenated files and generate CSV content
        fastq_files = glob.glob(os.path.join(args.input_seqs_directory, "**", "*.fastq.gz"), recursive=True)

        for fastq_file_path in fastq_files:
            file = os.path.basename(fastq_file_path)
            # Extract barcode from filename (format: barcode##_runaccession.fastq.gz)
            barcode = file.split('_')[0]
            file_id = file.replace('.fastq.gz', '').replace(f'{barcode}_', '')

            # Check if this barcode is in the metadata
            if barcode in valid_barcodes:
                # Create sample ID
                sample = barcode

                # Set instrument platform
                instrument_platform = "OXFORD_NANOPORE"

                # Set path to fastq file (full absolute path)
                fastq_1 = os.path.abspath(fastq_file_path)

                # Write row to CSV
                csv_writer.writerow([sample, file_id, instrument_platform, fastq_1])
                processed_files.append(barcode)
            else:
                skipped_files.append(barcode)

    # Report on the processing
    print_info(f"Sample CSV file created at: {args.output_csv_file}")
    print_info(f"Number of samples included: {len(processed_files)}")

    # Report any missing barcodes from metadata that weren't found in files
    missing_barcodes = [b for b in valid_barcodes if b not in processed_files]
    if missing_barcodes:
        print_warning(
            f"{len(missing_barcodes)} barcodes specified in the metadata were not found in the input files: {', '.join(missing_barcodes)}")

    # Report any files that were skipped
    if skipped_files:
        print_info(
            f"Found {len(skipped_files)} barcodes that were not specified in the metadata, skipping : {', '.join(skipped_files)}")


if __name__ == "__main__":
    main()
