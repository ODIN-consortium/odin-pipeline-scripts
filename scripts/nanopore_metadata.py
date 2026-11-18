import warnings
import functools
import logging
import pandas as pd
import os
import re

# Suppress openpyxl Data Validation warning
warnings.filterwarnings("ignore", message="Data Validation extension is not supported and will be removed")

logger = logging.getLogger(__name__)

def set_column_dtypes(df: pd.DataFrame, dtype_dict: dict) -> pd.DataFrame:
    """
    Set the data types for specific columns in a DataFrame.

    Parameters:
        df (pd.DataFrame): The input DataFrame
        dtype_dict (dict): Dictionary mapping column names to their desired data types

    Returns:
        pd.DataFrame: DataFrame with updated data types
    """
    df_copy = df.copy()
    for col, dtype in dtype_dict.items():
        if col in df_copy.columns:
            try:
                df_copy[col] = df_copy[col].astype(dtype)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to convert column '{col}' to {dtype}: {e}")
        else:
            logger.warning(f"Column '{col}' not found in DataFrame")

    return df_copy


def extract_site_and_type_from_sample_id(sample_id: str):
    """
    Extract sampling_site_id and sample_type from sample_id.
    Assumes sample_id is in the format: {sampling_site_id}_{sample_type}_*

    Returns:
        tuple: (sampling_site_id, sample_type) or (None, None) if not matched
    """
    match = re.match(r'^([^_]+)_([^_]+)(?:_|$)', sample_id)
    if match:
        return match.group(1), match.group(2)
    else:
        return None, None

def load_sample_lookup(metadata_file: str) -> dict[str, tuple[str, str]]:
    """``sample_code`` -> (site_ID, sample_type), from the ``samples`` sheet.

    This is where odin_pipeline takes ``sampling_site_id`` and ``sample_type`` from (the sample's
    own site and type), so a two-part type such as ``SG_G`` or ``SG_P`` stays whole and a site
    whose ID contains an underscore (``DVDVRV_N``) is not cut short. The same ``sample_code`` has
    one site and one type however many dates it was sampled on; a clash is logged and the first
    row kept.
    """
    samples_df = read_samples_df(metadata_file)
    lookup: dict[str, tuple[str, str]] = {}
    if samples_df is None or not {'sample_code', 'site_ID', 'sample_type'} <= set(samples_df.columns):
        return lookup
    for _, row in samples_df.iterrows():
        code, site, sample_type = (str(row[c]).strip() if pd.notna(row[c]) else '' for c in
                                   ('sample_code', 'site_ID', 'sample_type'))
        if not code or not site or not sample_type:
            continue
        if code in lookup and lookup[code] != (site, sample_type):
            logger.warning(f"sample_code '{code}' has more than one site/type in the samples sheet: "
                           f"{lookup[code]} and {(site, sample_type)}. Using the first.")
            continue
        lookup.setdefault(code, (site, sample_type))
    return lookup


def site_and_type(sample_code, sample_id, lookup: dict[str, tuple[str, str]] | None):
    """(sampling_site_id, sample_type) of a nanopore row.

    From the ``samples`` sheet when the row's ``sample_code`` is there (see ``load_sample_lookup``);
    otherwise parsed from ``sample_id`` as before, which cuts a two-part type or a site ID with an
    underscore short, so it is logged.
    """
    code = '' if sample_code is None or (isinstance(sample_code, float) and pd.isna(sample_code)) \
        else str(sample_code).strip()
    if lookup and code in lookup:
        return lookup[code]
    site, sample_type = extract_site_and_type_from_sample_id(str(sample_id))
    if site:
        logger.warning(f"sample_code '{code}' not found in the samples sheet; read site '{site}' and type "
                       f"'{sample_type}' from sample_id '{sample_id}' instead")
    return site, sample_type


def read_nanopore_metadata(metadata_file):
    metadata_df = pd.read_excel(
        metadata_file,
        sheet_name="nanopore",
        header=1,
        skiprows=[2],  # skip line 3 (0-based index)
        dtype=str
    )
    logger.debug(
        f'Loaded metadata_df with {len(metadata_df)} rows from {metadata_file}, sheet "nanopore". Read columns: {metadata_df.columns.tolist()}')
    required_cols = ["sampling_date", "barcode", "sample_id", "run_accession"]
    metadata_df = ensure_columns(metadata_df, required_cols)
    return metadata_df

def load_sites_df(metadata_file):
    """
    Load sites information from the metadata Excel file.

    Reads the 'sites' sheet from the metadata file, ensures required columns are present,
    and sets the correct data types for longitude and latitude.

    Parameters:
        metadata_file (str): Path to the metadata Excel file

    Returns:
        pd.DataFrame: DataFrame containing site information
    """
    sites_df = pd.read_excel(
        metadata_file,
        sheet_name="sites",
        header=0,
        skiprows=[1],  # skip line 2 (0-based index)
        dtype=str
    )
    logger.debug(
        f'Loaded sites_df with {len(sites_df)} rows from {metadata_file}, sheet "sites". Read columns: {sites_df.columns.tolist()}')
    sites_df = ensure_columns(sites_df, ['site_ID', 'country', 'longitude', 'latitude'])
    # Set numeric types for longitude and latitude
    sites_df = set_column_dtypes(sites_df, {
        'longitude': 'float64',
        'latitude': 'float64'
    })
    return sites_df


def read_samples_df(metadata_file: str) -> pd.DataFrame | None:
    """
    Load the samples sheet from the metadata Excel file.

    Parameters:
        metadata_file (str): Path to the metadata Excel file

    Returns:
        pd.DataFrame containing the samples sheet, or None on error
    """
    try:
        samples_df = pd.read_excel(
            metadata_file,
            sheet_name="samples",
            header=0,
            skiprows=[1],  # skip line 2 (0-based index)
            dtype=str
        )
        samples_df = samples_df.dropna(how='all')
        logger.debug(
            f'Loaded samples_df with {len(samples_df)} rows from {metadata_file}. Columns: {samples_df.columns.tolist()}')
        return samples_df
    except Exception as e:
        logger.warning(f"Could not load samples sheet from {metadata_file}: {e}")
        return None


def get_run_metadata(metadata_file, run_accession, run_name=None, sample_name=None):
    """
    Retrieve metadata for a specific run_accession, optionally filtering by runName and sampleName.

    Args:
        metadata_file (str): Path to the metadata Excel file
        run_accession (str): Run accession ID to look for
        run_name (str, optional): Run name to further filter the result
        sample_name (str, optional): Sample name to further filter the result

    Returns:
        dict: Dictionary with metadata for the specified run_accession

    Raises:
        ValueError: If multiple different values are found for sampling_date
        ValueError: If no matching metadata is found
    """
    metadata_df = read_nanopore_metadata(metadata_file)

    # Find the row with matching run_accession
    run_data = metadata_df[metadata_df["run_accession"] == run_accession]

    # Apply additional filters if provided
    if run_name and len(run_data) > 0:
        run_data = run_data[run_data["runName"] == run_name]

    if sample_name and len(run_data) > 0:
        run_data = run_data[run_data["sampleName"] == sample_name]

    if len(run_data) == 0:
        error_msg = f"No metadata found for run_accession: {run_accession}, runName: {run_name}, sampleName: {sample_name}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if all matching rows have the same sampling_date
    unique_dates = run_data["sampling_date"].unique()

    if len(unique_dates) > 1:
        error_msg = f"Multiple sampling_date values found for run_accession {run_accession}: {unique_dates}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Return a dictionary with the important metadata fields
    result = {
        "sample_id": run_data["sample_id"].iloc[0],
        "sampling_date": unique_dates[0],
    }
    if "sample_code" in run_data.columns:
        result["sample_code"] = run_data["sample_code"].iloc[0]

    return result

def extract_run_components(run_path):
    """
    Extract the runName, sampleName, and run_accession from a path.

    Args:
        run_path (str): Path containing runName/sampleName/run_accession structure

    Returns:
        tuple: (run_name, sample_name, run_accession)
    """
    parts = run_path.strip('/').split('/')
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    elif len(parts) == 2:
        return parts[0], parts[1], ""
    elif len(parts) == 1:
        return "", "", parts[0]
    else:
        return "", "", ""

def ensure_columns(df: pd.DataFrame, required_columns: list[str]) -> pd.DataFrame:
    """
    Ensure that the dataframe has the specified columns, renaming them if necessary.
    Raises ValueError if any required columns are missing.
    :param df: DataFrame to check
    :param required_columns: required columns, case-sensitive
    :return: DataFrame with the required columns
    """
    col_dict = {col.strip().lower(): col for col in required_columns}
    for col in df.columns:
        col_lower = col.strip().lower()
        if col not in required_columns and col_lower in col_dict:
            # Rename the column to match the expected name
            df.rename(columns={col: col_dict[col_lower]}, inplace=True)
    # Check if all required columns are present
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        logger.error(f'Missing columns in dataframe: {missing_cols}')
        raise ValueError(f'Missing columns in dataframe: {missing_cols}')
    return df


# MinKNOW names a run directory {YYYYMMDD}_{HHMM}_{instrument}_{flow_cell_id}_{protocol_run_id},
# e.g. 20250912_0843_MN00000_FBD00001_44c4f359. The flow cell is read from that name.
# Only the date and time fields are checked: instrument names can carry a hyphen
# (MD-000000) and flow cell IDs vary in shape (FBD00001, ABC001), so the instrument and
# flow cell are taken as whatever lies between the underscores.
_MINKNOW_DIR_RE = re.compile(r"^\d{8}_\d{4}_[^_]+_([^_]+)_[^_]+$")


@functools.lru_cache(maxsize=None)
def flow_cell_of(run_accession: str):
    """The flow cell ID in a MinKNOW run directory name, or None when the name has none.

    A name without one is logged (once per name): such a run is never merged with another.
    """
    m = _MINKNOW_DIR_RE.match(str(run_accession))
    if not m:
        logger.warning(f'Run name {run_accession!r} is not a MinKNOW run directory name; '
                       f'no flow cell read from it, so it will not be merged with any other run.')
        return None
    return m.group(1)


def same_flow_cell(ra1: str, ra2: str) -> bool:
    """True when both runs are known to be loadings of one flow cell."""
    fc = flow_cell_of(ra1)
    return fc is not None and fc == flow_cell_of(ra2)


def get_connected_run_accessions(metadata_df: pd.DataFrame, run_accession: str) -> pd.DataFrame:
    """Rows of the runs that are to be processed together with *run_accession*.

    Two runs are connected when the same barcode holds the same sample_id and sampling_date
    in both and they are loadings of one flow cell. A sample sequenced again on another flow
    cell is a separate sequencing event, never merged: it stays a replicate. A run whose
    name does not give a flow cell is connected to nothing.

    Returns an empty frame when *run_accession* has no connected run.
    """
    run_df = metadata_df[metadata_df['run_accession'] == run_accession]
    df = pd.DataFrame()
    for (sample_id, sampling_date, barcode), group in run_df.groupby(
            ['sample_id', 'sampling_date', 'barcode']):
        tmp = metadata_df.loc[
            (metadata_df['sample_id'] == sample_id) & (metadata_df['sampling_date'] == sampling_date) & (
                    metadata_df['barcode'] == barcode)]
        run_accessions = [ra for ra in tmp['run_accession'].unique().tolist()
                          if ra == run_accession or same_flow_cell(run_accession, ra)]
        if len(run_accessions) > 1:
            df = pd.concat([df, tmp[tmp['run_accession'].isin(run_accessions)]])
    return df

def merge_with_existing_file(new_df: pd.DataFrame, run_accessions: set[str], existing_file: str,
                             exclude_cols: set[str] | None = None) -> pd.DataFrame:
    """Merge a new dataframe with an existing feather file if present.

    Rows in the existing file whose 'run_accession' value is in the provided run_accessions set
    are removed prior to concatenation. Deduplication is performed across all columns except those
    listed in exclude_cols (defaults to {'run_accession', 'incomplete_data'} if present in columns).

    Parameters:
      new_df: Newly created dataframe.
      run_accessions: Set of run_accession identifiers represented in new_df.
      existing_file: Path to existing feather file.
      exclude_cols: Optional columns to exclude from deduplication subset logic.

    Returns:
      Merged, deduplicated dataframe (or new_df if existing not found / load fails).
    """
    if not os.path.exists(existing_file):
        return new_df
    try:
        existing_df = pd.read_feather(existing_file)
    except Exception as e:
        logger.warning(f"Could not read existing feather file '{existing_file}': {e}. Using only new data.")
        return new_df
    if 'run_accession' in existing_df.columns:
        existing_df = existing_df[~existing_df['run_accession'].isin(run_accessions)]
    logger.info(f'Merging with existing data from file {existing_file}, length: {len(existing_df)}, new data length: {len(new_df)}')
    merged_df = pd.concat([existing_df, new_df], ignore_index=True)
    if exclude_cols is None:
        exclude_cols = {'run_accession', 'runName'}
        if 'incomplete_data' in merged_df.columns:
            exclude_cols.add('incomplete_data')
    dedup_cols = [c for c in merged_df.columns if c not in exclude_cols]
    try:
        merged_df.drop_duplicates(subset=dedup_cols, inplace=True, keep='first')
    except Exception as e:
        logger.warning(f"Deduplication failed: {e}. Proceeding without dropping duplicates.")
    merged_df.reset_index(drop=True, inplace=True)
    logger.info(f"Merged dataset ({len(merged_df)} total rows after merge)")
    return merged_df

def warn_list(prefix: str, str_set: set[str]):
    """Log a warning listing items in a set with a prefix if the set is non-empty."""
    if str_set:
        joined = '\n'.join(sorted(str(item) for item in str_set))
        logger.warning(f"{prefix}\n{joined}")
