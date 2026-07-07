#!/usr/bin/env python3
"""
Combine all-country Kraken target-group feathers with AMR summary columns.

Strategy
--------
AMR data is at gene-hit level (one row per gene per sample); Kraken data is at
taxon level (one row per taxon per sample).  A direct join would produce a
cartesian explosion.  Instead:

  1. Aggregate AMR to SAMPLE level:
       - amr_classes        : sorted semicolon-separated resistance classes detected
       - amr_gene_count     : number of distinct AMR gene descriptions
       - amr_multi_resistant: True if any hit carries ≥2 resistance classes
       - amr_read_total     : total AMR read count across all genes in the sample

  2. Concatenate all-country Kraken target-group feathers.

  3. Left-join the AMR summary onto the Kraken rows by sample_id.

  4. Save as:
       {output_dir}/All_Countries_taxprofiler_target_group.feather
       {output_dir}/All_Countries_taxprofiler_target_group.xlsx  (if requested)

The resulting flat table can be loaded directly into Enlighten.  Each Kraken row
(a pathogen detection) carries the AMR context for that sample.

Usage
-----
    python combine_kraken_amr.py [--enlighten-dir DIR] [--amr-feather PATH]
                                 [--min-amr-reads N] [--xlsx]

Defaults
--------
    --enlighten-dir   (required — path to directory with per-country feather files)
    --amr-feather     (required — path to amr_data.feather)
    --min-amr-reads   5
"""

import sys
import argparse
import pandas as pd
from pathlib import Path

# ── Argument parsing ──────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument(
    '--enlighten-dir',
    required=True,
    help='Directory containing per-country *_taxprofiler_target_group.feather files'
)
parser.add_argument(
    '--amr-feather',
    required=True,
    help='Path to amr_data.feather produced by parse_amr_json.py'
)
parser.add_argument(
    '--output-dir',
    default=None,
    help='Output directory (default: same as --enlighten-dir)'
)
parser.add_argument(
    '--min-amr-reads', type=int, default=5,
    help='Minimum read count to count an AMR gene hit as detected (default: 5)'
)
parser.add_argument(
    '--xlsx', action='store_true',
    help='Also save an Excel (.xlsx) copy of the combined dataset'
)
args = parser.parse_args()

enlighten_dir = Path(args.enlighten_dir)
amr_path      = Path(args.amr_feather)
output_dir    = Path(args.output_dir) if args.output_dir else enlighten_dir
output_dir.mkdir(parents=True, exist_ok=True)

COUNTRIES = ['Tanzania', 'Burkina Faso', 'Democratic Republic of Congo']
MIN_AMR_READS = args.min_amr_reads

# ── 1. Concatenate all-country Kraken feathers ────────────────────────────────
print("Loading Kraken target-group feathers...")
kraken_parts = []
for country in COUNTRIES:
    path = enlighten_dir / f'{country}_taxprofiler_target_group.feather'
    if not path.exists():
        print(f"  WARNING: not found — {path}")
        continue
    df = pd.read_feather(path)
    print(f"  {country}: {len(df):,} rows, {df['sample_id'].nunique()} samples")
    kraken_parts.append(df)

if not kraken_parts:
    print("ERROR: No Kraken feathers found. Check --enlighten-dir.")
    sys.exit(1)

kraken = pd.concat(kraken_parts, ignore_index=True)
print(f"Combined Kraken: {len(kraken):,} rows, {kraken['sample_id'].nunique()} samples, "
      f"{kraken['country'].nunique()} countries\n")

# ── 2. Load and aggregate AMR data to sample level ────────────────────────────
print(f"Loading AMR feather: {amr_path}")
if not amr_path.exists():
    print(f"ERROR: AMR feather not found: {amr_path}")
    sys.exit(1)

amr_raw = pd.read_feather(amr_path)

# Keep only passing alignments above read threshold
if 'pass_status' in amr_raw.columns:
    amr_raw = amr_raw[amr_raw['pass_status']].copy()
amr_raw['count'] = pd.to_numeric(amr_raw['count'], errors='coerce').fillna(0)
amr_raw = amr_raw[amr_raw['count'] >= MIN_AMR_READS].copy()
print(f"  {len(amr_raw):,} gene hits after pass/count filter "
      f"({amr_raw['sample_id'].nunique()} samples)\n")

# Explode semicolon-separated resistance strings to one class per row
amr_expanded = (
    amr_raw[['sample_id', 'resistance', 'gene_description', 'count', 'multi_resistance']]
    .assign(resistance_class=lambda d: d['resistance'].fillna('unknown').str.split(';'))
    .explode('resistance_class')
)
amr_expanded['resistance_class'] = amr_expanded['resistance_class'].str.strip().str.lower()
amr_expanded = amr_expanded[amr_expanded['resistance_class'] != '']

# Aggregate per sample
print("Aggregating AMR to sample level...")
amr_sample = (
    amr_expanded.groupby('sample_id')
    .agg(
        amr_classes=('resistance_class', lambda s: ';'.join(sorted(s.unique()))),
        amr_gene_count=('gene_description', 'nunique'),
        amr_read_total=('count', 'sum'),
    )
    .reset_index()
)
# Multi-resistance: any hit with multi_resistance flag
multi_flag = (
    amr_raw[amr_raw['multi_resistance'] == True]
    .groupby('sample_id')
    .size()
    .reset_index(name='_mdr_count')
)
amr_sample = amr_sample.merge(multi_flag, on='sample_id', how='left')
amr_sample['amr_multi_resistant'] = amr_sample['_mdr_count'].notna() & (amr_sample['_mdr_count'] > 0)
amr_sample.drop(columns=['_mdr_count'], inplace=True)

print(f"  AMR summary rows: {len(amr_sample)} (one per sample with any AMR detection)")
print(f"  Example:\n{amr_sample.head(3).to_string(index=False)}\n")

# ── 3. Left-join AMR summary onto Kraken rows ─────────────────────────────────
print("Joining AMR summary onto Kraken rows (left join on sample_id)...")
combined = kraken.merge(amr_sample, on='sample_id', how='left')

# Fill NaN AMR columns for samples with no AMR data
combined['amr_classes']        = combined['amr_classes'].fillna('')
combined['amr_gene_count']     = combined['amr_gene_count'].fillna(0).astype(int)
combined['amr_read_total']     = combined['amr_read_total'].fillna(0).astype(int)
combined['amr_multi_resistant'] = combined['amr_multi_resistant'].fillna(False)

n_with_amr = (combined['amr_gene_count'] > 0).sum()
samples_with_amr = combined.loc[combined['amr_gene_count'] > 0, 'sample_id'].nunique()
print(f"  Combined rows: {len(combined):,}")
print(f"  Rows with AMR data: {n_with_amr:,} ({samples_with_amr} samples)\n")

# ── 4. Save ───────────────────────────────────────────────────────────────────
out_feather = output_dir / 'All_Countries_taxprofiler_target_group.feather'
combined.reset_index(drop=True, inplace=True)
combined.to_feather(out_feather)
print(f"✓ Saved feather: {out_feather}")

if args.xlsx:
    out_xlsx = output_dir / 'All_Countries_taxprofiler_target_group.xlsx'
    combined.to_excel(out_xlsx, index=False)
    print(f"✓ Saved xlsx:    {out_xlsx}")

print("\nNew columns added to each Kraken row:")
print("  amr_classes         — semicolon-separated resistance classes detected in sample")
print("  amr_gene_count      — number of distinct AMR genes detected in sample")
print("  amr_read_total      — total AMR read count across all genes in sample")
print("  amr_multi_resistant — True if any multi-drug-resistance hit detected in sample")
print("\n⚠ These are sample-level co-detections, not per-taxon AMR assignments.")
