#!/usr/bin/env python3
import sys
import logging
import os
from nanopore_metadata import get_run_metadata, extract_run_components, extract_site_and_type_from_sample_id

def main():
    if len(sys.argv) < 3:
        print("Usage: python get_run_metadata.py <metadata_file> <run_accession> [<run_path>]")
        sys.exit(1)

    metadata_file = sys.argv[1]
    run_accession = sys.argv[2]
    run_path = sys.argv[3] if len(sys.argv) > 3 else run_accession

    # Extract runName and sampleName from the path
    run_name, sample_name, _ = extract_run_components(run_path)

    # Get metadata for the run accession
    metadata = get_run_metadata(metadata_file, run_accession, run_name, sample_name)

    if metadata:
        sample_id = metadata.get('sample_id', '')
        sampling_site_id, _ = extract_site_and_type_from_sample_id(sample_id)
        print(f"sampling_site_id={sampling_site_id if sampling_site_id else ''}")
        print(f"sampling_date={metadata.get('sampling_date', '')}")
        sys.exit(0)
    else:
        print("ERROR: Could not find metadata for the specified run_accession")
        sys.exit(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
