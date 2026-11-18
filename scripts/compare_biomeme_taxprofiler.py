#!/usr/bin/env python3
"""
Cross-reference Biomeme and Taxprofiler findings for matching sample + date + pathogen.

For each of the three country taxprofiler feathers (Tanzania, Burkina Faso,
Democratic Republic of Congo) finds rows in BiomemeAssay.feather that share:
  - sample_code
  - sampling_date
  - pathogen  (taxprofiler: "Priority pathogen group"  <->  biomeme: "Pathogen")

Three Excel files are produced per country:
  {Country}_comparison_exact.xlsx          — case-insensitive exact string match
  {Country}_comparison_fuzzy.xlsx          — prefix / similarity match (includes exact)
  {Country}_comparison_presence_not_false.xlsx  — fuzzy matches where biomeme Presence
                                             contains "true" (e.g. "true", "true_x")

Columns use _t (taxprofiler) and _b (biomeme) suffixes on overlapping names.
The join keys (sample_code, sampling_date) and the two pathogen columns appear
once each without a suffix for easy comparison.

Usage
-----
    python compare_biomeme_taxprofiler.py [--enlighten-dir DIR] [--output-dir DIR]
                                          [--fuzzy-threshold FLOAT]

Defaults
--------
    --enlighten-dir    $ODIN_DATA_ROOT/data_custom_db_v6/enlighten (required if ODIN_DATA_ROOT is unset)
    --fuzzy-threshold  0.75
"""

import sys
import os
import re
import argparse
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd

# ── Argument parsing ──────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
)

_data_root = os.environ.get('ODIN_DATA_ROOT', '')

parser.add_argument(
    '--enlighten-dir',
    default=os.path.join(_data_root, 'data_custom_db_v6', 'enlighten') if _data_root else None,
    help='Directory containing per-country taxprofiler feathers and BiomemeAssay.feather '
         '(default: $ODIN_DATA_ROOT/data_custom_db_v6/enlighten)',
)
parser.add_argument(
    '--output-dir',
    default=None,
    help='Directory to write output Excel files (default: same as --enlighten-dir)',
)
parser.add_argument(
    '--fuzzy-threshold',
    type=float,
    default=0.75,
    help='Minimum similarity ratio (0–1) for fuzzy pathogen matching (default: 0.75)',
)
args = parser.parse_args()
if not args.enlighten_dir:
    parser.error('give --enlighten-dir, or set ODIN_DATA_ROOT')

enlighten_dir = Path(args.enlighten_dir)
output_dir    = Path(args.output_dir) if args.output_dir else enlighten_dir
output_dir.mkdir(parents=True, exist_ok=True)

COUNTRIES   = ['Tanzania', 'Burkina Faso', 'Democratic Republic of Congo']
T_PATHOGEN  = 'Priority pathogen group'   # taxprofiler column
B_PATHOGEN  = 'Pathogen'                  # biomeme column
B_PRESENCE  = 'Presence'                  # biomeme presence column
JOIN_KEYS   = ['sample_code', 'sampling_date']


# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalise(s: str) -> str:
    """Lowercase and strip trailing taxonomic qualifiers for fuzzy comparison."""
    s = str(s).lower().strip()
    s = re.sub(r'\s+s[sp]p?\.\s*$', '', s)   # spp. / sp.
    s = re.sub(r'\s+subsp\.\s*$', '', s)
    s = re.sub(r'\s+var\.\s*$', '', s)
    s = re.sub(r'[^a-z0-9 ]+$', '', s)        # trailing punctuation
    return s.strip()


def _fuzzy_match(a: str, b: str, threshold: float) -> bool:
    na, nb = _normalise(a), _normalise(b)
    if na == nb:
        return True
    if na.startswith(nb) or nb.startswith(na):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Join keys → pathogen pair → _b columns (biomeme) → _t columns (taxprofiler) → everything else."""
    path_t = next((c for c in [T_PATHOGEN, T_PATHOGEN + '_t'] if c in df.columns), None)
    path_b = next((c for c in [B_PATHOGEN, B_PATHOGEN + '_b'] if c in df.columns), None)
    path_cols = [c for c in [path_b, path_t] if c]
    fixed = set(JOIN_KEYS + path_cols)
    b_cols = sorted(c for c in df.columns if c.endswith('_b') and c not in fixed)
    t_cols = sorted(c for c in df.columns if c.endswith('_t') and c not in fixed)
    fixed.update(b_cols + t_cols)
    other  = [c for c in df.columns if c not in fixed]
    ordered = JOIN_KEYS + path_cols + b_cols + t_cols + other
    return df[[c for c in ordered if c in df.columns]]


def _normalise_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Strip time component from sampling_date so date-only matching works."""
    df = df.copy()
    if pd.api.types.is_datetime64_any_dtype(df['sampling_date']):
        df['sampling_date'] = df['sampling_date'].dt.normalize()
    else:
        df['sampling_date'] = pd.to_datetime(df['sampling_date'], errors='coerce').dt.normalize()
    return df


def _filter_presence_not_false(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where the biomeme Presence column does not contain 'false' (case-insensitive).

    Keeps rows with values like 'true', 'true_x', empty/NaN, or any non-false value.
    After merging, the column may be named 'Presence', 'Presence_b', or similar.
    """
    candidates = [B_PRESENCE, B_PRESENCE + '_b', B_PRESENCE.lower(), B_PRESENCE.lower() + '_b']
    col = next((c for c in candidates if c in df.columns), None)
    if col is None:
        return df.iloc[0:0].copy()  # empty with same columns
    mask = ~df[col].astype(str).str.contains('false', case=False, na=False)
    return df[mask].reset_index(drop=True)


def make_exact(tp: pd.DataFrame, biomeme: pd.DataFrame) -> pd.DataFrame:
    """Case-insensitive inner join on sample_code + sampling_date + pathogen."""
    t = tp.copy()
    b = biomeme.copy()
    t['__pk'] = t[T_PATHOGEN].str.lower().str.strip()
    b['__pk'] = b[B_PATHOGEN].str.lower().str.strip()
    merged = t.merge(b, on=JOIN_KEYS + ['__pk'], how='inner', suffixes=('_t', '_b'))
    merged.drop(columns='__pk', inplace=True)
    merged.drop_duplicates(inplace=True)
    merged.reset_index(drop=True, inplace=True)
    return _reorder_columns(merged)


def make_fuzzy(
    tp: pd.DataFrame,
    biomeme: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame:
    """
    Fuzzy-match rows on sample_code + sampling_date + pathogen similarity.

    Includes all matches (also those covered by the exact file).
    Strategy: find unique pathogen pairs for shared (sample_code, sampling_date),
    apply fuzzy filter, then rejoin full rows.
    """
    # Unique pathogen values per join-key combination
    t_keys = tp[JOIN_KEYS + [T_PATHOGEN]].drop_duplicates()
    b_keys = biomeme[JOIN_KEYS + [B_PATHOGEN]].drop_duplicates()
    pairs  = t_keys.merge(b_keys, on=JOIN_KEYS, how='inner')

    if pairs.empty:
        return pd.DataFrame()

    pairs['_match'] = pairs.apply(
        lambda r: _fuzzy_match(r[T_PATHOGEN], r[B_PATHOGEN], threshold), axis=1
    )
    fuzzy_pairs = pairs[pairs['_match']].drop(columns='_match').copy()

    if fuzzy_pairs.empty:
        return pd.DataFrame()

    result = (
        fuzzy_pairs
        .merge(tp,      on=JOIN_KEYS + [T_PATHOGEN], how='left')
        .merge(biomeme, on=JOIN_KEYS + [B_PATHOGEN], how='left', suffixes=('_t', '_b'))
    )
    result.drop_duplicates(inplace=True)
    result.reset_index(drop=True, inplace=True)
    return _reorder_columns(result)


# ── Load biomeme ──────────────────────────────────────────────────────────────
biomeme_path = enlighten_dir / 'BiomemeAssay.feather'
if not biomeme_path.exists():
    print(f"ERROR: BiomemeAssay.feather not found in {enlighten_dir}")
    sys.exit(1)

print(f"Loading biomeme: {biomeme_path}")
biomeme = pd.read_feather(biomeme_path)
biomeme = _normalise_dates(biomeme)
print(f"  {len(biomeme):,} rows, {biomeme[B_PATHOGEN].nunique()} unique pathogens, "
      f"{biomeme['sample_code'].nunique()} samples")

if B_PATHOGEN not in biomeme.columns:
    print(f"ERROR: biomeme feather has no '{B_PATHOGEN}' column. Found: {list(biomeme.columns)}")
    sys.exit(1)

# ── Process each country ──────────────────────────────────────────────────────
total_exact          = 0
total_exact_presence = 0
total_fuzzy          = 0
total_presence       = 0

for country in COUNTRIES:
    tp_path = enlighten_dir / f'{country}_taxprofiler.feather'
    if not tp_path.exists():
        print(f"\nWARNING: not found — {tp_path}")
        continue

    print(f"\n── {country} " + "─" * (60 - len(country)))
    tp = pd.read_feather(tp_path)
    tp = _normalise_dates(tp)
    print(f"  taxprofiler : {len(tp):,} rows, {tp[T_PATHOGEN].nunique()} unique pathogens, "
          f"{tp['sample_code'].nunique()} samples")

    if T_PATHOGEN not in tp.columns:
        print(f"  WARNING: no '{T_PATHOGEN}' column in {tp_path.name}, skipping")
        continue

    # ── Exact ─────────────────────────────────────────────────────────────────
    exact = make_exact(tp, biomeme)
    print(f"  exact       : {len(exact):,} matched rows")
    total_exact += len(exact)

    if not exact.empty:
        out = output_dir / f'{country}_comparison_exact.xlsx'
        exact.to_excel(out, index=False)
        print(f"  ✓ {out.name}")

    exact_presence_not_false = _filter_presence_not_false(exact) if not exact.empty else pd.DataFrame()
    print(f"  exact+presence≠false: {len(exact_presence_not_false):,} matched rows")
    total_exact_presence += len(exact_presence_not_false)

    if not exact_presence_not_false.empty:
        out = output_dir / f'{country}_comparison_exact_presence_not_false.xlsx'
        exact_presence_not_false.to_excel(out, index=False)
        print(f"  ✓ {out.name}")

    # ── Fuzzy ─────────────────────────────────────────────────────────────────
    fuzzy = make_fuzzy(tp, biomeme, args.fuzzy_threshold)
    print(f"  fuzzy       : {len(fuzzy):,} matched rows "
          f"(threshold={args.fuzzy_threshold}, includes exact matches)")
    total_fuzzy += len(fuzzy)

    if not fuzzy.empty:
        # Show which pathogen pairs were matched for transparency
        if T_PATHOGEN in fuzzy.columns and B_PATHOGEN in fuzzy.columns:
            pairs_shown = (
                fuzzy[[T_PATHOGEN, B_PATHOGEN]]
                .drop_duplicates()
                .rename(columns={T_PATHOGEN: 'taxprofiler', B_PATHOGEN: 'biomeme'})
            )
            print("    Fuzzy pairs found:")
            for _, r in pairs_shown.iterrows():
                print(f"      '{r['taxprofiler']}' ~ '{r['biomeme']}'")

        out = output_dir / f'{country}_comparison_fuzzy.xlsx'
        fuzzy.to_excel(out, index=False)
        print(f"  ✓ {out.name}")

    # ── Presence = true ───────────────────────────────────────────────────────
    presence_true = _filter_presence_not_false(fuzzy) if not fuzzy.empty else pd.DataFrame()
    print(f"  presence≠false: {len(presence_true):,} matched rows")
    total_presence += len(presence_true)

    if not presence_true.empty:
        out = output_dir / f'{country}_comparison_fuzzy_presence_not_false.xlsx'
        presence_true.to_excel(out, index=False)
        print(f"  ✓ {out.name}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nDone: {total_exact} exact rows ({total_exact_presence} with presence≠false), "
      f"{total_fuzzy} fuzzy rows ({total_presence} with presence≠false) "
      f"across all countries.")
