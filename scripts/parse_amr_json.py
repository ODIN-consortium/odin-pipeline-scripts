#!/usr/bin/env python3
"""
Parse AMR JSON files from Nextflow wf-metagenomics output and create a pandas DataFrame.

Updated: Now only reads AMR JSON files for run_accessions/barcodes present in the provided metadata Excel.
Directory discovery mirrors logic in create_kraken_datasets.py but uses
'nanopore_processed/outputs_wf_metagenomics_amr/<dir_option>'.
"""

import argparse
import glob
import json
import logging
import os
import sys
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

from nanopore_metadata import (
    read_nanopore_metadata,
    load_sites_df,
    extract_site_and_type_from_sample_id,
    get_connected_run_accessions,
    merge_with_existing_file,
    warn_list,
)

# ── Short-code helpers ────────────────────────────────────────────────────────
_VOWELS = frozenset("aeiou")
_SPECIAL_CODES = {"penam": "pnam", "penem": "pnem"}


def _make_drug_code(name: str) -> str:
    """Return a 4-letter code: first letter + next 3 consonants (vowels skipped).

    Examples:
        fluoroquinolone -> flrq
        carbapenem      -> crbp
        cephalosporin   -> cphl
        cephamycin      -> cphm   (unambiguous with cephalosporin)
        aminoglycoside  -> amng
        aminocoumarin   -> amnc   (unambiguous with aminoglycoside)
        glycopeptide    -> glcp
        glycylcycline   -> glcl   (unambiguous with glycopeptide)
        nitroimidazole  -> ntrm
        nitrofuran      -> ntrf   (unambiguous with nitroimidazole)
        penam           -> pnam   (special: too few consonants)
        penem           -> pnem   (special: too few consonants)
    """
    name = name.lower().strip()
    if name in _SPECIAL_CODES:
        return _SPECIAL_CODES[name]
    consonants = [c for c in name[1:] if c.isalpha() and c not in _VOWELS]
    return (name[0] + "".join(consonants[:3])).ljust(4, "x")[:4]


def parse_amr_json_file(file_path, run_accession=None):
    """
    Parse a single AMR JSON file and extract data.

    Args:
        file_path (str): Path to the JSON file
        run_accession (str): Identifier for the run (parent folder of 'amr')

    Returns:
        list: List of dictionaries containing the parsed data (one row per resistance token if semicolon-separated)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []
    records = []
    for barcode_key, barcode_data in data.items():
        if not isinstance(barcode_data, dict):
            continue
        pass_status = barcode_data.get('pass', None)
        results = barcode_data.get('results', {})
        for gene_description, gene_data in results.items():
            meta_list = gene_data.get('meta', [])
            for meta in meta_list:
                resistance_all = meta.get('RESISTANCE')
                resistance_tokens = resistance_all.split(';') if resistance_all else [None]
                short_name = ';'.join([_make_drug_code(t) for t in resistance_tokens if t]) if resistance_tokens else None
                record = {
                    'run_accession': run_accession,
                    'barcode': barcode_key,
                    'pass_status': pass_status,
                    'gene_description': gene_description,
                    'multi_resistance': len(resistance_tokens) > 1 if resistance_tokens else False,
                    'resistance': resistance_all,
                    'short_name': short_name,
                    'count': gene_data.get('count', 0),
                    'sequence': meta.get('SEQUENCE'),
                    'start': meta.get('START'),
                    'end': meta.get('END'),
                    'coverage_percent': meta.get('%COVERAGE'),
                    'identity_percent': meta.get('%IDENTITY'),
                    'file': file_path,
                }
                records.append(record)
    return records


def _find_amr_files_for_barcode(base_path: str, barcode: str) -> List[str]:
    """Find AMR json files for a specific barcode within a discovered base_path.

    We search patterns:
      base_path/amr/{barcode}.amr.json
      base_path/**/amr/{barcode}.amr.json (recursive)
    """
    patterns = [
        os.path.join(base_path, 'amr', f'{barcode}.amr.json'),
        os.path.join(base_path, '**', 'amr', f'{barcode}.amr.json'),
    ]
    found = []
    for pattern in patterns:
        found.extend(glob.glob(pattern, recursive=True))
    # Deduplicate
    return sorted(set(found))


def create_amr_dataframe_from_metadata(metadata_file: str, data_folder: str) -> Tuple[pd.DataFrame, set]:
    """Build AMR dataframe based on metadata-defined run_accessions & barcodes.

    Mirrors directory selection logic from create_kraken_datasets.create_kraken_dataset_from_metadata
    but uses outputs_wf_metagenomics_amr.

    Returns dataframe and set of processed run_accessions (original, not merged list).
    """
    sites_df = load_sites_df(metadata_file)
    metadata_df = read_nanopore_metadata(metadata_file)
    # Keep rows with non-empty barcode
    metadata_df = metadata_df.loc[
        (metadata_df['barcode'].notna()) & (metadata_df['barcode'].astype(str).str.strip() != '')]
    df_out = pd.DataFrame()
    missing_dirs = set()
    missing_files = set()
    missing_barcodes = set()
    empty_runs = set()
    processed_run_accessions = set()
    logger.info(f'Creating AMR dataset from metadata: {metadata_file}. Rows with barcodes: {len(metadata_df)}')

    for _, row in metadata_df.iterrows():
        run_accession = str(row['run_accession'])
        barcode = str(row['barcode']).strip()
        if not barcode:
            missing_barcodes.add(run_accession)
            continue
        # Determine directory options order based on connected runs
        keep = get_connected_run_accessions(metadata_df, run_accession)
        connected_run_accessions = keep['run_accession'].unique() if not keep.empty else []
        if not keep.empty:
            dir_options = [str(row['sampleName']), f'merged_{run_accession}', run_accession]
        else:
            dir_options = [run_accession, str(row['sampleName']), f'merged_{run_accession}']
        # Build candidate directories
        candidate_dirs = [
            os.path.join(data_folder, 'nanopore_processed', 'outputs_wf_metagenomics_amr', opt)
            for opt in dir_options
        ]
        base_path = candidate_dirs[0]
        for cdir in candidate_dirs:
            if os.path.isdir(cdir):
                base_path = cdir
                break
        if not os.path.isdir(base_path):
            missing_dirs.add(run_accession)
            continue
        logger.info(
            f"Processing run_accession:{row['run_accession']}, barcode: {barcode}, sampleName: {row['sampleName']}, from directory: {base_path}")
        # Find amr json files for this barcode under base_path
        files = _find_amr_files_for_barcode(base_path, barcode)
        if not files:
            missing_files.add(run_accession)
            continue
        is_incomplete = (not keep.empty) and base_path.endswith(run_accession)
        run_accs = connected_run_accessions if not keep.empty else [run_accession]
        for f in files:
            records = parse_amr_json_file(f, run_accession=run_accession if is_incomplete else ','.join(run_accs))
            if not records:
                continue
            tmp_df = pd.DataFrame(records)
            tmp_df['incomplete_data'] = is_incomplete
            # attach basic metadata columns to allow later enrichment (avoid duplicate merges inflating rows)
            for meta_col in ['sample_id', 'sample_code', 'sampling_date', 'protocol_id', 'sequencing_kit_id', 'barcode',
                             'alias', 'type', 'runName', 'sampleName', 'run_accession']:
                if meta_col in row and meta_col not in tmp_df.columns:
                    tmp_df[meta_col] = row[meta_col]
            df_out = pd.concat([df_out, tmp_df], axis=0)
        processed_run_accessions.add(run_accession)

    # Warn
    warn_list("Missing AMR directories for run_accessions:", missing_dirs)
    warn_list("No AMR JSON files for run_accessions (given barcode):", missing_files)
    warn_list("Missing barcode in metadata for run_accessions:", missing_barcodes)
    warn_list("Empty parsed AMR data for run_accessions:", empty_runs)

    if df_out.empty:
        return df_out, processed_run_accessions

    # Deduplicate
    dedup_cols = [c for c in df_out.columns if c not in {'incomplete_data'}]
    df_out.drop_duplicates(subset=dedup_cols, inplace=True)

    # Enrich with site info
    df_out = merge_with_sites_df(df_out, sites_df)
    return df_out, processed_run_accessions


def merge_with_sites_df(df: pd.DataFrame, sites_df: pd.DataFrame) -> pd.DataFrame:
    df['country'] = None
    df['lon'] = None
    df['lat'] = None
    if sites_df.empty:
        print("Sites DataFrame is empty; skipping merge.")
        return df
    sample_ids = df.get('sample_id')
    if sample_ids is None:
        return df
    sample_ids = sample_ids.unique()
    for sample_id in sample_ids:
        if pd.isna(sample_id):
            continue
        mask = df['sample_id'] == sample_id
        sampling_site_id, sample_type = extract_site_and_type_from_sample_id(sample_id)
        if sampling_site_id:
            df.loc[mask, 'sample_type'] = sample_type
            df.loc[mask, 'sampling_site_id'] = sampling_site_id
            site_row = sites_df[sites_df['site_ID'] == sampling_site_id]
            if site_row.empty:
                logger.warning(f'No site found for sampling_site_id: {sampling_site_id}')
                continue
            df.loc[mask, 'country'] = site_row.iloc[0]['country']
            df.loc[mask, 'lon'] = site_row.iloc[0]['longitude']
            df.loc[mask, 'lat'] = site_row.iloc[0]['latitude']
    return df


def create_summary(df: pd.DataFrame, out_dir: str, file_prefix: str):
    # Summarize by 'resistance'
    groups = ['resistance']
    for group in groups:
        if group not in df.columns:
            continue
        summary = df.groupby([group]).agg({
            'resistance': 'count',
            'run_accession': 'nunique',
            'barcode': 'nunique',
            'sequence': 'nunique',
            'coverage_percent': 'mean',
            'identity_percent': 'mean',
            'sample_id': lambda x: '; '.join(sorted(set(x.dropna().astype(str))))
        }).round(2)
        col_names = ['count', 'unique_run_accession', 'unique_barcodes', 'unique_sequence', 'avg_coverage',
                     'avg_identity', 'sample_ids']
        summary.columns = col_names
        summary.sort_values(by='count', ascending=False, inplace=True)
        if out_dir and file_prefix:
            file = f"{out_dir}/{file_prefix}_summary_by_{group}.csv"
            summary.to_csv(file, index=True)
            print(f"Summary saved to: {file}")
            try:
                summary.to_feather(file.replace('.csv', '.feather'))
            except Exception as e:
                print(f"Warning: could not save feather summary ({e})")
            try:
                summary.to_excel(file.replace('.csv', '.xlsx'))
            except Exception as e:
                print(f"Warning: could not save excel summary ({e})")


def main():
    parser = argparse.ArgumentParser(
        description="Parse AMR JSON files from Nextflow wf-metagenomics output using metadata-driven directory discovery"
    )
    parser.add_argument('--data_path', required=True, help='Root data path containing nanopore_processed directory')
    parser.add_argument('--metadata_excel', required=True, help='Metadata Excel file path')
    parser.add_argument('-o', '--output', required=True, help='Output directory path (will create amr_data.* files)')
    parser.add_argument('--show-summary', action='store_true', help='Show summary statistics')
    args = parser.parse_args()

    data_path = args.data_path
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(data_path):
        print(f"Error: data_path '{data_path}' does not exist")
        sys.exit(1)
    if not os.path.exists(args.metadata_excel):
        print(f"Error: metadata_excel '{args.metadata_excel}' does not exist")
        sys.exit(1)
    # Ensure output directory exists
    if os.path.isfile(output_dir):
        print(f"Error: --output must be a directory path, got existing file: {output_dir}")
        sys.exit(1)
    os.makedirs(output_dir, exist_ok=True)

    df, run_accessions = create_amr_dataframe_from_metadata(args.metadata_excel, data_path)
    if df.empty:
        print('No AMR JSON data found for metadata run_accessions/barcodes')
        sys.exit(1)

    # Merge with existing feather main dataset if exists
    feather_path = os.path.join(output_dir, 'amr_data.feather')
    df = merge_with_existing_file(df, run_accessions, feather_path)

    if args.show_summary:
        print('\n' + '=' * 50)
        print('SUMMARY STATISTICS')
        print('=' * 50)
        print(f'Total records: {len(df)}')
        print(f'Unique run_accessions: {df["run_accession"].nunique()}')
        print(f'Unique barcodes: {df["barcode"].nunique()}')
        if 'resistance' in df.columns:
            print(f'Unique resistance types: {df["resistance"].nunique()}')
        if 'pass_status' in df.columns:
            print('Pass status distribution:')
            print(df['pass_status'].value_counts())
        if 'resistance' in df.columns:
            print('\nTop 5 resistance types:')
            print(df['resistance'].value_counts().head())
        if 'barcode' in df.columns:
            print('\nResistance records per barcode:')
            print(df['barcode'].value_counts().head())
        if 'coverage_percent' in df.columns:
            try:
                print(f'\nAverage coverage: {pd.to_numeric(df["coverage_percent"], errors="coerce").mean():.2f}%')
            except Exception:
                pass
        if 'identity_percent' in df.columns:
            try:
                print(f'Average identity: {pd.to_numeric(df["identity_percent"], errors="coerce").mean():.2f}%')
            except Exception:
                pass

    # Standard output filenames
    csv_path = os.path.join(output_dir, 'amr_data.csv')
    feather_path = os.path.join(output_dir, 'amr_data.feather')
    excel_path = os.path.join(output_dir, 'amr_data.xlsx')

    try:
        df.to_csv(csv_path, index=False)
        print(f'Data saved to CSV: {csv_path}')
    except Exception as e:
        print(f'Warning: could not save CSV file ({e})')
    try:
        df.to_feather(feather_path)
        print(f'Data saved to Feather: {feather_path}')
    except Exception as e:
        print(f'Warning: could not save Feather file ({e})')
    try:
        df.to_excel(excel_path, index=False)
        print(f'Data saved to Excel: {excel_path}')
    except Exception as e:
        print(f'Warning: could not save Excel file ({e})')

    # Show first rows if summary not requested
    if not args.show_summary:
        print('\n' + '=' * 50)
        print('FIRST 10 ROWS')
        print('=' * 50)
        print(df.head(10))

    # Summaries use fixed prefix
    file_prefix = 'amr_data'
    create_summary(df, output_dir, file_prefix)


if __name__ == '__main__':
    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)],
                        format='%(levelname)-6s: "%(message)s" ( function=%(funcName)s() Line %(lineno)-4d)',
                        encoding='utf-8', level='INFO')
    main()
