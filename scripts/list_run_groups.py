#!/usr/bin/env python3
"""
List one representative run_accession per merge group from the MinKNOW data directory.

A "merge group" is a set of run_accessions that share the same sample_id, sampling_date,
and barcode in the metadata — i.e. runs that should be concatenated together before
being processed by the pipeline.

For each group, this script outputs the relative path of a single representative
(runName/sampleName/runAccession) on stdout. The wrapper script passes each of these
to start_nextflow.sh / start_nextflow_amr.sh with --auto-merge, which handles the
full merge automatically.

Run accessions found on disk but absent from the metadata are listed on stderr and skipped.

Usage:
    python list_run_groups.py --minknow_data_dir <dir> --metadata_file <file>
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nanopore_metadata import read_nanopore_metadata, get_connected_run_accessions

logger = logging.getLogger(__name__)


def find_run_accessions_on_disk(minknow_data_dir: str) -> list[tuple[str, str]]:
    """
    Find all run_accessions on disk that have processable fastq data.

    Mirrors the logic of select_run_accession() in config_utils.sh:
    looks for fastq_pass/ dirs that contain at least one barcode*/ subdir
    with at least one *.fastq.gz file.

    Returns:
        List of (relative_path, run_accession_name) tuples, where relative_path
        is runName/sampleName/runAccession relative to minknow_data_dir.
    """
    root = Path(minknow_data_dir)
    results = []
    seen = set()

    for fastq_pass in root.rglob("fastq_pass"):
        if not fastq_pass.is_dir():
            continue
        # Check for at least one barcode dir with fastq.gz files
        has_data = any(
            list(bd.glob("*.fastq.gz"))
            for bd in fastq_pass.glob("barcode*")
            if bd.is_dir()
        )
        if not has_data:
            continue

        run_accession_dir = fastq_pass.parent
        rel_path = run_accession_dir.relative_to(root)
        rel_str = str(rel_path).replace("\\", "/")
        run_accession_name = run_accession_dir.name

        if rel_str not in seen:
            seen.add(rel_str)
            results.append((rel_str, run_accession_name))

    return sorted(results)


def compute_run_groups(metadata_file: str, run_accession_names: list[str]) -> list[list[str]]:
    """
    Group run_accessions by their merge relationships.

    Returns a list of groups; each group is a list of run_accession names.
    The first element of each group is the representative (alphabetically first).
    """
    metadata_df = read_nanopore_metadata(metadata_file)
    metadata_df = metadata_df.dropna(subset=["run_accession", "barcode", "sample_id", "sampling_date"])

    # Restrict to run_accessions we actually have on disk
    on_disk = set(run_accession_names)
    metadata_df = metadata_df[metadata_df["run_accession"].isin(on_disk)]

    groups = []
    assigned = set()

    for ra in sorted(run_accession_names):
        if ra in assigned:
            continue
        connected = get_connected_run_accessions(metadata_df, ra)
        if not connected.empty:
            group = sorted(
                ra_name for ra_name in connected["run_accession"].unique()
                if ra_name in on_disk
            )
        else:
            group = [ra]

        if not set(group).issubset(assigned):
            groups.append(group)
            assigned.update(group)

    return groups


def main():
    parser = argparse.ArgumentParser(
        description="List one representative run_accession per merge group for batch processing."
    )
    parser.add_argument("--minknow_data_dir", required=True,
                        help="Directory containing MinKNOW output folders")
    parser.add_argument("--metadata_file", required=True,
                        help="Path to metadata Excel file")
    args = parser.parse_args()

    # Find everything on disk
    on_disk = find_run_accessions_on_disk(args.minknow_data_dir)
    if not on_disk:
        print("No run_accessions with fastq data found in the MinKNOW directory.", file=sys.stderr)
        sys.exit(1)

    rel_path_by_name = {name: rel for rel, name in on_disk}
    run_accession_names = list(rel_path_by_name.keys())

    # Determine merge groups from metadata
    try:
        groups = compute_run_groups(args.metadata_file, run_accession_names)
    except Exception as e:
        print(f"ERROR: Failed to read metadata: {e}", file=sys.stderr)
        sys.exit(1)

    # Output one representative relative path per group (the first alphabetically)
    for group in groups:
        representative_name = group[0]
        representative_path = rel_path_by_name.get(representative_name)
        if representative_path:
            if len(group) > 1:
                others = ", ".join(group[1:])
                print(f"# Merge group: {', '.join(group)}", file=sys.stderr)
            print(representative_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    main()
