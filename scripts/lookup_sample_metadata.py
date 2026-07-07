#!/usr/bin/env python3
"""Look up sample metadata from the ODIN metadata Excel workbook.

Usage:
    python lookup_sample_metadata.py <metadata_file> <barcode> <run_accession> <script_dir>

Outputs KEY=VALUE lines to stdout, ready for bash eval:
    META_FOUND=yes|no|error
    META_SAMPLE_CODE=...
    META_SAMPLE_ID=...
    META_SAMPLE_TYPE_CODE=...
    META_SAMPLE_TYPE_DESC=...
    META_SAMPLING_DATE=...
    META_SITE_ID=...
    META_SITE=...
    META_CITY=...
    META_COUNTRY=...
    META_PARTNER_CODE=...
    META_COMMENTS=...
"""

import sys
import os

# Allow importing nanopore_metadata from the scripts directory
script_dir = sys.argv[4] if len(sys.argv) > 4 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

def _load_sample_type_descriptions(metadata_file: str) -> dict:
    """Read sample_type → description from lookup_tables sheet, columns H and I."""
    try:
        import pandas as pd
        df = pd.read_excel(metadata_file, sheet_name='lookup_tables',
                           header=None, dtype=str, usecols=[7, 8])
        df.columns = ['code', 'description']
        df = df.dropna(subset=['code'])
        # Skip the header row (code == 'sample_type')
        df = df[df['code'].str.strip() != 'sample_type']
        return {
            row['code'].strip(): row['description'].strip()
            for _, row in df.iterrows()
            if str(row['description']).strip() not in ('nan', 'None', '')
        }
    except Exception:
        return {}


def _clean(val) -> str:
    """Return a clean single-line string, or empty string for NaN/None."""
    if val is None:
        return ''
    s = str(val).strip()
    return '' if s.lower() in ('nan', 'none', 'nat') else s


def emit(key: str, val: str) -> None:
    # Newlines inside a value would break bash eval — collapse to space
    print(f'{key}={val.replace(chr(10), " ").replace(chr(13), "")}')


def main():
    if len(sys.argv) < 4:
        emit('META_FOUND', 'error')
        emit('META_ERROR', 'Usage: lookup_sample_metadata.py <metadata_file> <barcode> <run_accession> [script_dir]')
        sys.exit(1)

    metadata_file = sys.argv[1]
    barcode       = sys.argv[2].lower().strip()
    run_accession = sys.argv[3].strip()

    try:
        from nanopore_metadata import read_nanopore_metadata, read_samples_df, load_sites_df
    except ImportError as e:
        emit('META_FOUND', 'error')
        emit('META_ERROR', f'Cannot import nanopore_metadata: {e}')
        sys.exit(1)

    if not os.path.isfile(metadata_file):
        emit('META_FOUND', 'error')
        emit('META_ERROR', f'Metadata file not found: {metadata_file}')
        sys.exit(1)

    try:
        nano = read_nanopore_metadata(metadata_file)

        bc_mask  = nano['barcode'].str.lower().str.strip() == barcode
        run_mask = nano['run_accession'].str.strip() == run_accession if 'run_accession' in nano.columns else bc_mask

        row_df = nano[bc_mask & run_mask]
        # For merged runs, the taxprofiler output uses sampleName as the run_accession identifier
        # (e.g. SAMPLE15_BF), not the actual flowcell run_accession — try sampleName next.
        if row_df.empty and 'sampleName' in nano.columns:
            sn_mask = nano['sampleName'].str.strip() == run_accession
            row_df = nano[bc_mask & sn_mask]
        if row_df.empty:
            row_df = nano[bc_mask]  # fallback: barcode only, any run

        if row_df.empty:
            emit('META_FOUND', 'no')
            sys.exit(0)

        row = row_df.iloc[0]
        sample_id     = _clean(row.get('sample_id'))
        sampling_date = _clean(row.get('sampling_date'))
        run_acc_found = _clean(row.get('run_accession'))

        # site_id is always the first underscore-delimited segment of sample_id
        site_id = sample_id.split('_')[0] if sample_id else ''

        # Look up sample_code, sample_type, partner_code, comments from the samples sheet.
        # Match by finding the samples row whose sample_code is a prefix of sample_id
        # (sample_id = sample_code + "_" + replicate/filter suffix).
        # When multiple rows share the same sample_code, prefer the one whose sampling_date matches.
        sample_code      = ''
        sample_type_code = ''
        partner_code     = ''
        comments         = ''
        try:
            samples = read_samples_df(metadata_file)
            if samples is not None and sample_id:
                best_row  = None
                best_len  = 0
                date_matched = False
                for _, srow in samples.iterrows():
                    sc = _clean(srow.get('sample_code', ''))
                    if not sc:
                        continue
                    # sample_id must start with sample_code followed by '_' or equal it
                    if sample_id == sc or sample_id.startswith(sc + '_'):
                        sc_date_match = _clean(srow.get('sampling_date', '')) == sampling_date
                        # Prefer longer sample_code (more specific); within same length prefer date match
                        if (len(sc) > best_len
                                or (len(sc) == best_len and sc_date_match and not date_matched)):
                            best_row     = srow
                            best_len     = len(sc)
                            date_matched = sc_date_match
                if best_row is not None:
                    sample_code      = _clean(best_row.get('sample_code', ''))
                    sample_type_code = _clean(best_row.get('sample_type', ''))
                    partner_code     = _clean(best_row.get('partner_sample_code', ''))
                    comments         = _clean(best_row.get('comments_sampling', ''))
        except Exception:
            pass  # samples sheet optional

        # Fall back to parsing from sample_id if the samples sheet lookup found nothing.
        # sample_type may be two segments (e.g. SG_G, SG_P) or one (WW, DW, RW …).
        if not sample_type_code:
            parts = sample_id.split('_')
            two_part = f'{parts[1]}_{parts[2]}' if len(parts) >= 3 else ''
            if two_part and two_part in SAMPLE_TYPE_DESCRIPTIONS:
                sample_type_code = two_part
            elif len(parts) >= 2:
                sample_type_code = parts[1]

        if not sample_code:
            sample_code = f'{site_id}_{sample_type_code}' if sample_type_code else sample_id

        sample_type_descriptions = _load_sample_type_descriptions(metadata_file)
        sample_type_desc = sample_type_descriptions.get(sample_type_code, sample_type_code)

        # Sites sheet
        country = city = site_name = ''
        try:
            sites = load_sites_df(metadata_file)
            if sites is not None and site_id:
                smask = sites['site_ID'].astype(str).str.strip() == site_id
                if smask.any():
                    srow = sites[smask].iloc[0]
                    country   = _clean(srow.get('country', ''))
                    city      = _clean(srow.get('city', ''))
                    site_name = _clean(srow.get('site', ''))
        except Exception:
            pass  # sites sheet optional

        emit('META_FOUND',            'yes')
        emit('META_SAMPLE_CODE',      sample_code)
        emit('META_SAMPLE_ID',        sample_id)
        emit('META_SAMPLE_TYPE_CODE', sample_type_code)
        emit('META_SAMPLE_TYPE_DESC', sample_type_desc)
        emit('META_SAMPLING_DATE',    sampling_date)
        emit('META_SITE_ID',          site_id)
        emit('META_SITE',             site_name)
        emit('META_CITY',             city)
        emit('META_COUNTRY',          country)
        emit('META_PARTNER_CODE',     partner_code)
        emit('META_COMMENTS',         comments)

    except Exception as e:
        emit('META_FOUND', 'error')
        emit('META_ERROR', str(e).replace('\n', ' '))
        sys.exit(1)


if __name__ == '__main__':
    main()
