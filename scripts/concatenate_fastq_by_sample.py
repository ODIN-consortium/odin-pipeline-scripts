#!/usr/bin/env python3
"""
Script to concatenate fastq files from multiple run_accessions that share the same sample_id or for a specific run_accession.

This script:
1. Reads metadata to find all run_accessions with the given sample_id or the specific run_accession
2. Finds all fastq_pass directories under those run_accessions in minknow_data_dir
3. Filters barcodes to only include those present in the metadata
4. Concatenates fastq.gz files by barcode across all matching run_accessions
5. Outputs one concatenated file per barcode in the tmp_dir

Usage:
    python concatenate_fastq_by_sample.py <minknow_data_dir> <output_dir> --sample_id <sample_id> <metadata_file> <tmp_dir>
    python concatenate_fastq_by_sample.py <minknow_data_dir> <output_dir> --run_accession <run_accession> <metadata_file> <tmp_dir>
"""

import argparse
import logging
import os
import subprocess
import sys
from glob import glob
from pathlib import Path

import pandas as pd

from nanopore_metadata import read_nanopore_metadata, get_connected_run_accessions


class ColorFormatter(logging.Formatter):
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    RESET = '\033[0m'

    def format(self, record):
        msg = super().format(record)
        if record.levelno == logging.WARNING:
            msg = f"\n{self.WARNING}{msg}{self.RESET}\n"
        elif record.levelno >= logging.ERROR:
            msg = f"\n{self.FAIL}{msg}{self.RESET}\n"
        return msg


# Set up logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColorFormatter('%(levelname)s - %(message)s'))
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
logger = logging.getLogger(__name__)


def display_run_accession_table_and_prompt(metadata_df, input_run_accession):
    """
    Display a table of run_accessions found and prompt user to choose whether to use all or just the input one.

    Args:
        metadata_df (DataFrame): The filtered metadata dataframe
        input_run_accession (str): The run_accession provided as input

    Returns:
        bool: True if user wants to use all run_accessions, False if only the input one
    """
    # Color codes
    BLUE = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RESET = '\033[0m'

    # Get unique combinations of the key columns
    table_data = metadata_df[['sampleName', 'sample_id', 'sampling_date', 'barcode', 'run_accession']].drop_duplicates()
    table_data = table_data.sort_values(['sample_id', 'sampling_date', 'barcode', 'run_accession'])

    print(f"\n{GREEN}You provided run_accession: {input_run_accession}{RESET}")
    print(f"\n{YELLOW}Found the following run_accessions with matching sample_id and sampling_date:{RESET}")
    print("=" * 120)
    print(f"{'sampleName':<25} {'sample_id':<25} {'sampling_date':<14} {'barcode':<11} {'run_accession':<40}")
    print("-" * 120)

    for _, row in table_data.iterrows():
        sample_name = str(row['sampleName'])[:25] if pd.notna(row['sampleName']) else 'N/A'
        sample_id = str(row['sample_id'])[:25] if pd.notna(row['sample_id']) else 'N/A'
        sampling_date = str(row['sampling_date'])[:14] if pd.notna(row['sampling_date']) else 'N/A'
        barcode = str(row['barcode'])[:11] if pd.notna(row['barcode']) else ''
        run_accession = str(row['run_accession'])[:40] if pd.notna(row['run_accession']) else 'N/A'
        print(f"{sample_name:<25} {sample_id:<25} {sampling_date:<14} {barcode:<11} {run_accession:<40}")

    print("=" * 120)

    print("Do you want to:")
    print("1. Concatenate fastq files from ALL related run_accessions shown above")
    print("2. Concatenate fastq files from ONLY the provided run_accession")
    while True:
        print("Enter your choice (1 or 2): ")
        choice = input().strip()

        if choice == "1":
            print(f'{GREEN}Using all run_accessions for concatenation.{RESET}\n')
            return True  # Use all run_accessions
        elif choice == "2":
            print(f'{GREEN}Using only the provided run_accession: {input_run_accession}{RESET}\n')
            return False  # Use only the input run_accession
        else:
            print("Invalid choice. Please enter 1 or 2.")


def get_metadata_info(metadata_file, identifier, identifier_type, auto_merge=False, saved_choice=None):
    """
    Get run_accessions and valid barcodes for a specific run_accession or sample_id from the metadata file.

    Args:
        metadata_file (str): Path to the metadata Excel file
        identifier (str): The run_accession or sample_id to filter by
        identifier_type (str): Either 'run_accession' or 'sample_id'
        auto_merge (bool): If True, automatically merge all related run_accessions without prompting
        saved_choice (bool or None): If True/False, use this pre-saved merge decision and skip the prompt.
            None means prompt the user interactively.

    Returns:
        tuple: (list of run_accessions, dict of barcode -> metadata info, use_all bool)
    """
    try:
        # Read metadata
        metadata_df = read_nanopore_metadata(metadata_file)
        metadata_df = metadata_df.dropna(subset=['run_accession', 'barcode', 'sample_id', 'sampling_date'])

        # Filter by the specified identifier
        filtered_df = metadata_df[metadata_df[identifier_type] == identifier]

        if filtered_df.empty:
            logger.error(f"No metadata found for {identifier_type}: {identifier}")
            sys.exit(1)
        use_all = False
        # Handle run_accession input with user prompt
        if identifier_type == 'run_accession':
            # group by sample_id, sampling_date and barcode to get only the rows that should be merged with this run_accession
            keep = get_connected_run_accessions(metadata_df, identifier)
            if not keep.empty:
                # Determine merge decision: saved_choice takes priority, then auto_merge, then prompt
                if saved_choice is not None:
                    use_all = saved_choice
                elif auto_merge:
                    use_all = True
                else:
                    use_all = display_run_accession_table_and_prompt(keep, identifier)

                if use_all:
                    filtered_df = keep
                else:
                    # Keep only the original input run_accession
                    filtered_df = metadata_df[metadata_df[identifier_type] == identifier]
            # If keep is empty, we already have only the single run_accession, so no need to prompt

        run_accessions = filtered_df['run_accession'].dropna().unique()
        # Group by barcode and check sampling_date consistency within each barcode
        barcode_metadata = {}
        for barcode, group in filtered_df.groupby('barcode'):
            if pd.isna(barcode) or not str(barcode).strip():
                continue

            # Check consistency
            unique_ids = group['sample_id'].dropna().unique()
            unique_dates = group['sampling_date'].dropna().unique()
            unique_sample_names = group['sampleName'].dropna().unique()

            if len(unique_ids) != 1 or len(unique_dates) != 1 or len(unique_sample_names) != 1:
                logger.error(f"Inconsistent metadata for barcode '{barcode}': "
                             f"sample_ids={unique_ids.tolist()}, dates={unique_dates.tolist()}, "
                             f"sampleNames={unique_sample_names.tolist()}")
                sys.exit(1)

            barcode_metadata[barcode] = {
                'sample_id': unique_ids[0],
                'sampleName': unique_sample_names[0],
                'sampling_date': unique_dates[0],
                'run_accessions': set(group['run_accession'].dropna())
            }

        if not barcode_metadata:
            logger.error(f"No valid barcode values found for {identifier_type}: {identifier}")
            sys.exit(1)

        logger.info(
            f"Found {len(run_accessions)} run_accessions for {identifier_type} '{identifier}': {run_accessions}")
        logger.info(f"Found {len(barcode_metadata)} valid barcodes: {list(barcode_metadata.keys())}")

        # validate that for all barcodes the sampleNames there is only the set of run_accessions that we are processing.
        # No other run_accession - barcode combinations should be found in the original metadata_df
        if identifier_type == 'run_accession' and use_all:
            for barcode, info in barcode_metadata.items():
                other_run_accessions = set(metadata_df.loc[(metadata_df['barcode'] == barcode) & (
                            metadata_df['sampleName'] == info['sampleName']), 'run_accession'].dropna()) - info[
                                           'run_accessions']
                if other_run_accessions:
                    logger.warning(
                        f"Barcode '{barcode}' is associated with run_accessions {other_run_accessions} not in the selected set {info['run_accessions']}. All barcodes must be unique to the selected run_accessions.")

        return run_accessions, barcode_metadata, use_all

    except Exception as e:
        logger.error(f"Failed to read metadata file: {e}")
        sys.exit(1)


def find_fastq_directories(minknow_data_dir, run_accessions):
    """
    Find fastq_pass directories for the given run_accessions under minknow_data_dir.

    Args:
        minknow_data_dir (str): Base directory to search
        run_accessions (list): List of run_accession IDs to find

    Returns:
        dict: Mapping of run_accession -> fastq_pass directory path
    """
    fastq_pass_dirs = {}

    for run_accession in run_accessions:
        # Search for directories containing the run_accession
        pattern = os.path.join(minknow_data_dir, "**", run_accession)
        matches = glob(pattern, recursive=True)

        # Filter to only directories and find fastq_pass subdirectory
        for match in matches:
            if os.path.isdir(match):
                fastq_pass_path = os.path.join(match, "fastq_pass")
                if os.path.isdir(fastq_pass_path):
                    fastq_pass_dirs[run_accession] = Path(fastq_pass_path)
                    logger.info(f"Found fastq_pass for {run_accession}: {fastq_pass_path}")
                    break
        else:
            logger.warning(f"No fastq_pass directory found for run_accession: {run_accession}")

    return fastq_pass_dirs


def concatenate_fastq_files_by_metadata(fastq_pass_dirs, barcode_metadata, tmp_dir):
    """
    Concatenate fastq.gz files by iterating over barcode metadata and finding the corresponding directories.

    Args:
        fastq_pass_dirs (dict): Mapping of run_accession -> fastq_pass directory path
        barcode_metadata (dict): Mapping of barcode -> metadata info including run_accessions
        tmp_dir (str): Output directory for concatenated files

    Returns:
        tuple: (dict of barcode -> output file path, str identifier used for naming)
    """
    os.makedirs(tmp_dir, exist_ok=True)
    output_files = {}
    identifier = None  # Will store the identifier used for file naming

    for barcode, metadata in barcode_metadata.items():
        run_accessions = list(metadata['run_accessions'])
        logger.info(f"Processing {barcode} from {len(run_accessions)} run_accessions: {run_accessions}")
        sample_name = metadata.get('sampleName', None)
        is_merge = len(run_accessions) > 1
        current_identifier = metadata.get('sampleName', f'merged_{run_accessions[0]}') if is_merge else run_accessions[0]

        # Store the identifier (all barcodes should use the same identifier for consistency)
        if identifier is None:
            identifier = current_identifier

        # Collect all fastq.gz files from the expected barcode directories
        barcode_dir = os.path.join(tmp_dir, barcode)
        os.makedirs(barcode_dir, exist_ok=True)
        output_path = os.path.join(barcode_dir, f"{barcode}_{current_identifier}.fastq.gz")
        all_fastq_files = []

        for run_accession in run_accessions:
            if run_accession not in fastq_pass_dirs:
                logger.warning(f"No fastq_pass directory found for run_accession: {run_accession}")
                continue
            sample_name_dir = fastq_pass_dirs[run_accession].parent.parent.name
            if is_merge and sample_name and sample_name_dir != sample_name_dir:
                logger.warning(
                    f"Directory for {run_accession} is not in expected directory. Expected {sample_name}, found {sample_name_dir}")
            barcode_dir = os.path.join(fastq_pass_dirs[run_accession], barcode)

            if os.path.isdir(barcode_dir):
                fastq_files = glob(os.path.join(barcode_dir, "*.fastq.gz"))
                if fastq_files:
                    all_fastq_files.extend(fastq_files)
                    logger.debug(f"Found {len(fastq_files)} fastq.gz files in {barcode_dir}")
                else:
                    logger.warning(f"No fastq.gz files found in {barcode_dir}")
            else:
                logger.warning(f"Barcode directory not found: {barcode_dir}")

        if all_fastq_files:
            logger.info(f"Concatenating {len(all_fastq_files)} files for {barcode}")
            all_fastq_files.sort()  # Sort for consistent ordering

            try:
                # Use cat subprocess — far more efficient than Python file-by-file copy
                # for large numbers of files over DrvFs network mounts.
                with open(output_path, 'wb') as outfile:
                    result = subprocess.run(['cat'] + all_fastq_files, stdout=outfile, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    err = result.stderr.decode(errors='replace').strip()
                    raise IOError(f"cat exited with code {result.returncode}: {err}")

                output_files[barcode] = output_path
                logger.debug(f"Created concatenated file: {output_path}")
            except Exception as e:
                logger.error(f"Error concatenating files for {barcode}: {e}")
        else:
            logger.warning(f"No fastq.gz files found for {barcode}")

    return output_files, identifier


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate fastq files from multiple run_accessions sharing the same sample_id or for a specific run_accession"
    )
    parser.add_argument("--minknow_data_dir", help="Directory containing MinKNOW output folders", required=True)
    parser.add_argument("--output_dir", help="Root output directory (currently unused but kept for compatibility)",
                        required=True)

    # Create mutually exclusive group for run_accession and sample_id
    identifier_group = parser.add_mutually_exclusive_group(required=True)
    identifier_group.add_argument("--run_accession", type=str, help="Run accession to process")
    identifier_group.add_argument("--sample_id", type=str, help="Sample ID to find matching run_accessions")

    parser.add_argument("--metadata_file", help="Path to metadata Excel file", required=True)
    parser.add_argument("--tmp_dir", help="Temporary directory for concatenated files", required=True)
    parser.add_argument("--auto-merge", action="store_true", dest="auto_merge",
                        help="Automatically merge all related run_accessions without prompting")
    parser.add_argument("--resolve-identifier", action="store_true", dest="resolve_identifier",
                        help="Only resolve the file identifier from metadata and write it to "
                             ".fastq_identifier in tmp_dir, without concatenating any files")

    args = parser.parse_args()

    # Determine identifier type and value based on which argument was provided
    if args.run_accession:
        identifier_type = 'run_accession'
        identifier = args.run_accession
    else:  # args.sample_id
        identifier_type = 'sample_id'
        identifier = args.sample_id

    # Validate inputs
    if not os.path.isdir(args.minknow_data_dir):
        logger.error(f"MinKNOW data directory not found: {args.minknow_data_dir}")
        sys.exit(1)

    if not os.path.isfile(args.metadata_file):
        logger.error(f"Metadata file not found: {args.metadata_file}")
        sys.exit(1)

    if not os.path.isdir(args.tmp_dir):
        logger.info(f"Temporary directory does not exist, creating: {args.tmp_dir}")
        os.makedirs(args.tmp_dir, exist_ok=True)

    try:
        # Check for a saved merge choice from a prior --resolve-identifier call
        choice_file = os.path.join(args.tmp_dir, ".fastq_merge_choice")
        saved_choice = None
        if not args.resolve_identifier and os.path.isfile(choice_file):
            with open(choice_file, 'r') as f:
                val = f.read().strip()
            saved_choice = (val == "true")
            os.remove(choice_file)
            logger.debug(f"Using saved merge choice from previous step: {'all run_accessions' if saved_choice else 'single run_accession only'}")

        # Get metadata information
        run_accessions, barcode_metadata, use_all = get_metadata_info(args.metadata_file, identifier, identifier_type,
                                                             auto_merge=args.auto_merge, saved_choice=saved_choice)

        # Resolve the file identifier from metadata (same logic as concatenate_fastq_files_by_metadata)
        first_barcode = next(iter(barcode_metadata))
        first_meta = barcode_metadata[first_barcode]
        is_merge = len(first_meta['run_accessions']) > 1
        file_identifier = first_meta.get('sampleName', f'merged_{list(first_meta["run_accessions"])[0]}') if is_merge else list(first_meta['run_accessions'])[0]

        # If --resolve-identifier, save identifier and merge choice then exit early
        if args.resolve_identifier:
            os.makedirs(args.tmp_dir, exist_ok=True)
            identifier_file = os.path.join(args.tmp_dir, ".fastq_identifier")
            with open(identifier_file, 'w') as f:
                f.write(file_identifier)
            logger.info(f"Resolved identifier: '{file_identifier}'")
            # Save the user's merge choice so the second call can skip re-prompting
            with open(choice_file, 'w') as f:
                f.write("true" if use_all else "false")
            sys.exit(0)

        # Find fastq_pass directories for each run_accession
        logger.info("Finding fastq_pass directories...")
        fastq_pass_dirs = find_fastq_directories(args.minknow_data_dir, run_accessions)

        if not fastq_pass_dirs:
            logger.error("No fastq_pass directories found")
            sys.exit(1)

        # Concatenate files by iterating over barcode metadata
        logger.info("Concatenating fastq files...")
        output_files, file_identifier = concatenate_fastq_files_by_metadata(fastq_pass_dirs, barcode_metadata, args.tmp_dir)

        if output_files:
            logger.info(f"Successfully created {len(output_files)} concatenated files:")
            for barcode, output_path in output_files.items():
                logger.info(f"  {barcode}: {output_path}")

            # Write identifier to a temporary file for the bash script to read
            identifier_file = os.path.join(args.tmp_dir, ".fastq_identifier")
            with open(identifier_file, 'w') as f:
                f.write(file_identifier)
            logger.debug(f"Wrote identifier '{file_identifier}' to: {identifier_file}")
        else:
            logger.warning("No files were concatenated")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error during processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
