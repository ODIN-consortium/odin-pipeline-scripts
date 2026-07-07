import argparse
import datetime
import glob
import logging
import os
import sys
from difflib import get_close_matches
from typing import Literal

import yaml

import pandas as pd

from kraken_parser import read_kraken2_report, enrich_kraken2_lineage, RANK_COLUMN_MAPPING
from nanopore_metadata import read_nanopore_metadata, extract_site_and_type_from_sample_id, \
    set_column_dtypes, load_sites_df, get_connected_run_accessions, merge_with_existing_file, warn_list, read_samples_df

FEATHER_TYPE = 'feather'
XLSX_TYPE = 'xlsx'


class ColorFormatter(logging.Formatter):
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    RESET = '\033[0m'

    def format(self, record):
        msg = super().format(record)
        if record.levelno == logging.WARNING:
            msg = f"{self.WARNING}{msg}{self.RESET}"
        elif record.levelno >= logging.ERROR:
            msg = f"{self.FAIL}{msg}{self.RESET}"
        return msg


# Set up logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColorFormatter('%(levelname)s - %(message)s'))
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
logger = logging.getLogger(__name__)


def kraken2_to_dataframe(fpath: str, column_names: list[str]) -> pd.DataFrame:
    """
    Convert a Kraken2 report file to a pandas DataFrame with enriched lineage information.

    Parameters:
        fpath (str): Path to the Kraken2 report file
        column_names (list[str]): Column names for the Kraken2 report data

    Returns:
        pd.DataFrame: DataFrame containing the Kraken2 report data with enriched lineage information
    """
    df0 = read_kraken2_report(fpath, column_names)
    if df0.empty:
        logger.warning(f"Empty kraken2 report file: {fpath}. No data to process.")
        return pd.DataFrame()
    df = enrich_kraken2_lineage(df0, RANK_COLUMN_MAPPING)
    # remove lines with only root or unclassified
    # df = df[~df['Scientific name'].str.lower().isin(['unclassified', 'root'])]
    df.reset_index(drop=True, inplace=True)
    return df


def add_metadata(df: pd.DataFrame, metadata_row: pd.Series, sites_df: pd.DataFrame, metadata_file: str) -> pd.DataFrame:
    """
    Add metadata to the Kraken2 report DataFrame.

    Finds the country, longitude and latitude from the sites_df DataFrame based on the sampling_site_id.
    Extracts sample_type from the sample_id in the metadata_row and adds all metadata columns to the DataFrame.

    Parameters:
        df (pd.DataFrame): Kraken2 report DataFrame
        metadata_row (pd.Series): Row from the metadata DataFrame containing sample_id, sampling_date, barcode
        sites_df (pd.DataFrame): DataFrame containing site information with columns site_id, country, longitude, latitude
        metadata_file (str): Path to the metadata Excel file (used to load samples sheet for partner_sample_code)

    Returns:
        pd.DataFrame: DataFrame with added metadata information
    """
    # Extract sampling_site_id and sample_type from sample_id
    sample_id = metadata_row['sample_id']
    sampling_site_id, sample_type = extract_site_and_type_from_sample_id(sample_id)
    if sampling_site_id:
        site_row = sites_df[sites_df['site_ID'] == sampling_site_id]
        if site_row.empty:
            logger.warning(f'No site found for sampling_site_id: {sampling_site_id}')
            df['country'] = None
            df['lon'] = None
            df['lat'] = None
        else:
            df['country'] = site_row.iloc[0]['country']
            df['lon'] = site_row.iloc[0]['longitude']
            df['lat'] = site_row.iloc[0]['latitude']
    else:
        df['country'] = None
        df['lon'] = None
        df['lat'] = None

    # Add sample_type and sampling_site_id columns
    df['sample_type'] = sample_type
    df['sampling_site_id'] = sampling_site_id

    # add metadata columns to the dataframe
    use_cols = ['sample_code', 'sampling_date', 'protocol_id', 'sequencing_kit_id', 'barcode', 'sample_id', 'alias',
                'type', 'runName', 'sampleName', 'run_accession']
    for col in use_cols:
        if col not in df.columns:
            df[col] = metadata_row[col]  # Add metadata values to the dataframe

    # Merge partner_sample_code from the samples tab
    samples_df = read_samples_df(metadata_file)
    sample_code = metadata_row.get('sample_code', None)
    if samples_df is not None and sample_code is not None and 'partner_sample_code' in samples_df.columns:
        sample_row = samples_df[samples_df['sample_code'] == sample_code]
        df['partner_sample_code'] = sample_row['partner_sample_code'].iloc[0] if not sample_row.empty else None
    else:
        df['partner_sample_code'] = None

    return df


def create_kraken_dataset_from_metadata(metadata_file: str, data_folder: str, column_names: list[str],
                                        suffix: str = 'kraken2.report.txt') -> tuple[pd.DataFrame, set[str]]:
    """
    Create a comprehensive DataFrame from a metadata file with corresponding Kraken2 reports.

    This function iterates through the metadata file, locates corresponding Kraken2 reports based on
    run accession and barcode information, adds metadata to each report, and combines them into a single DataFrame.

    Parameters:
        metadata_file (str): Path to the metadata Excel file
        data_folder (str): Base path where the Kraken2 report files are stored
        column_names (list[str]): Column names for the Kraken2 report data
        suffix (str): File suffix for the Kraken2 report files (default: 'kraken2.report.txt')

    Returns:
        pd.DataFrame: Combined DataFrame with all Kraken2 report data and metadata
    """
    sites_df = load_sites_df(metadata_file)
    metadata_df = read_nanopore_metadata(metadata_file)
    # Skip rows with missing barcode values (NaN or empty string)
    metadata_df = metadata_df.loc[(metadata_df["barcode"].notna()) & (metadata_df["barcode"].str.strip() != "")]
    df = pd.DataFrame()
    missing_dirs_list = set()
    missing_barcodes_list = set()
    empty_list = set()
    run_accessions = set()
    logger.info(f"Creating Kraken2 dataset from metadata: {metadata_file}")
    logger.info(f"Number of metadata entries with barcodes: {len(metadata_df)}")
    for idx, row in metadata_df.iterrows():
        # Validate sampling_date format
        sampling_date = str(row["sampling_date"])
        try:
            datetime.datetime.strptime(sampling_date, "%Y%m%d")
        except (ValueError, TypeError) as e:
            logger.error(
                f"Invalid sampling_date format for sample_id:{row['sample_id']}: '{sampling_date}' (expected YYYYMMDD)")
            raise (e)
        # validate runName, sampleName, and run_accession
        run_accession = row["run_accession"]
        keep = get_connected_run_accessions(metadata_df, run_accession)
        connected_run_accessions = keep['run_accession'].unique() if not keep.empty else []
        if not keep.empty:
            dir_options = [str(row['sampleName']), str('merged_' + run_accession), str(run_accession)]
        else:
            dir_options = [str(run_accession), str(row['sampleName']), str('merged_' + run_accession)]
        dirs = [os.path.join(data_folder, 'nanopore_processed', 'outputs_taxprofiler', option) for option in
                dir_options]
        base_path = os.path.join(data_folder, 'nanopore_processed', 'outputs_taxprofiler', dir_options[0])
        for dir in dirs:
            if os.path.isdir(dir):
                base_path = dir
                break
        if not os.path.isdir(base_path):
            missing_dirs_list.add(run_accession)
            continue
        barcode = row["barcode"].strip()
        if not barcode:
            missing_barcodes_list.add(run_accession)
            continue
        logger.info(
            f"Processing run_accession:{row['run_accession']}, barcode: {barcode}, sampleName: {row['sampleName']}, from directory: {base_path}")
        is_incomplete = not keep.empty and base_path.endswith(str(run_accession))
        run_accs = connected_run_accessions if not keep.empty else [run_accession]
        if is_incomplete:
            logger.warning(
                f"Found {len(connected_run_accessions)} connected run_accessions for run_accession:{run_accession}: {', '.join(connected_run_accessions)}")
            logger.warning(
                f'Data for run_accession:{run_accession} is incomplete in directory {base_path} and will be marked as such.')

        tmp = create_kraken_dataset(base_path, column_names=column_names, prefix=barcode, suffix=suffix)
        if tmp.empty:
            empty_list.add(run_accession)
            continue
        run_accessions.add(run_accession)
        tmp = add_metadata(tmp, row, sites_df, metadata_file)
        tmp['sampling_date'] = pd.to_datetime(tmp['sampling_date'], errors='raise', format='%Y%m%d')
        tmp['incomplete_data'] = is_incomplete
        if not is_incomplete:
            tmp['run_accession'] = ','.join(run_accs)
        # Filter out empty or all-NA DataFrames before concatenation
        frames = [df, tmp]
        frames = [f for f in frames if not f.empty and not f.isna().all().all()]
        df = pd.concat(frames, axis=0)
    warn_list(f"No data found in '{data_folder}' for run_accessions:", missing_dirs_list)
    warn_list("No barcode found in metadata file for run_accessions:", missing_barcodes_list)
    warn_list("No valid entries found in kraken2 reports for run_accessions:", empty_list)
    # deduplicate df with subset=all columns except run_accession/incomplete_data/runName
    # runName can differ when the same kraken2 file is processed for split runs (e.g., part1/part2)
    # while sampleName, sample_id, barcode, and all kraken2 data remain identical
    dedup_cols = list(set(df.columns) - {'run_accession', 'incomplete_data', 'runName'})
    rows_before_dedup = len(df)
    df.drop_duplicates(subset=dedup_cols, inplace=True, keep='first')
    rows_removed = rows_before_dedup - len(df)
    if rows_removed > 0:
        logger.info(f'Removed {rows_removed} duplicate rows (differing only in runName/run_accession/incomplete_data)')
    df.reset_index(drop=True, inplace=True)
    return df, run_accessions

def split_dataset(df: pd.DataFrame, split_by: str) -> list[tuple[str, pd.DataFrame]]:
    """
    Split a DataFrame into subsets based on unique values in a specified column.

    Parameters:
        df (pd.DataFrame): The DataFrame to split
        split_by (str): The column name to split by

    Returns:
        list[tuple[str, pd.DataFrame]]: List of tuples containing (value, subset_df) for each unique value
    """
    # Check if split_by column exists in the dataframe
    if split_by not in df.columns:
        logger.error(
            f'Split by column {split_by} not found in dataframe columns: {df.columns}. Using default "country".')
        split_by = 'country'

    subsets = []
    unique_values = df[split_by].unique()
    for value in unique_values:
        # Create subset for this value
        subset_df = df[df[split_by] == value]
        if subset_df.empty:
            logger.warning(f'No data found for {split_by}={value}, skipping.')
            continue
        subsets.append((f'{value}_taxprofiler', subset_df))
    return subsets


def merge_datasets_with_existing(subsets: list[tuple[str, pd.DataFrame]], run_accessions: set[str], output_path: str) -> \
        list[tuple[str, pd.DataFrame]]:
    """
    Merge each subset dataframe with existing data in corresponding files.

    Parameters:
        subsets (list[tuple[str, pd.DataFrame]]): List of tuples with (value, subset_df)
        run_accessions (set[str]): Set of run accessions in the new data
        output_path (str): The directory containing existing files

    Returns:
        list[tuple[str, pd.DataFrame]]: List of tuples with (value, merged_df)
    """
    merged_subsets = []

    for name, subset_df in subsets:
        output_file = os.path.join(output_path, f'{name}.feather')

        # Merge with existing data if file exists
        merged_df = merge_with_existing_file(subset_df, run_accessions, output_file)
        merged_subsets.append((name, merged_df))

    return merged_subsets


def save_subsets(subsets: list[tuple[str, pd.DataFrame]], output_path: str,
                 ds_type: Literal[FEATHER_TYPE, XLSX_TYPE]) -> None:
    """
    Save each subset DataFrame to a feather file or an excel file depending on ds_type parameter.

    Parameters:
        subsets (list[tuple[str, pd.DataFrame]]): List of tuples with (name, subset_df)
        output_path (str): The directory to save the files
    """

    # Save merged datasets
    for name, subset_df in subsets:
        output_file = os.path.join(output_path, f'{name}.{ds_type}')

        # Save merged dataframe
        if ds_type == XLSX_TYPE:
            subset_df.to_excel(output_file, index=False)
        else:
            subset_df.to_feather(output_file)
        logger.info(f'Saved dataset with {len(subset_df)} rows to: {output_file}')


def create_target_groups(subsets: list[tuple[str, pd.DataFrame]]) -> list[tuple[str, pd.DataFrame]]:
    """
    Create target group subsets from the merged datasets.

    Filters each subset to include only rows where 'Target group' is not null,
    and returns a new list of tuples with name suffixed with '_target_group'.

    Parameters:
        subsets (list[tuple[str, pd.DataFrame]]): List of tuples with (name, subset_df)

    Returns:
        list[tuple[str, pd.DataFrame]]: List of tuples with (name_target_group, target_group_df)
    """
    target_groups = []
    for name, subset_df in subsets:
        # Handle target group subset - created from merged dataframe
        if 'Target group' in subset_df.columns:
            target_group_df = subset_df.loc[subset_df['Target group'].notna()]
            if not target_group_df.empty:
                df = target_group_df.copy()
                df.reset_index(drop=True, inplace=True)
                target_groups.append((f'{name}_target_group', df))
    return target_groups


def create_kraken_dataset(data_folder: str, column_names: list[str], prefix: str = 'barcode',
                          suffix: str = 'kraken2.report.txt') -> pd.DataFrame:
    """
    Create a DataFrame by combining all Kraken2 reports in a folder that match the specified pattern.

    Parameters:
        data_folder (str): Path to the folder containing Kraken2 reports
        column_names (list[str]): Column names for the Kraken2 report data
        prefix (str): File prefix to match (default: 'barcode')
        suffix (str): File suffix to match (default: 'kraken2.report.txt')

    Returns:
        pd.DataFrame: Combined DataFrame with all Kraken2 report data
    """
    df_out = pd.DataFrame()
    pattern = os.path.join(data_folder, f'**/{prefix}*{suffix}')
    logger.debug(f'Looking for kraken2 reports in {data_folder}')
    # Use glob.glob with recursive=True to search subdirectories
    found_files = glob.glob(pattern, recursive=True)
    if not found_files:
        logger.warning(f'No kraken2 reports found in {data_folder} with pattern: {pattern}')
        return df_out
    logger.debug(f'Found {len(found_files)} kraken2 reports in {data_folder} with pattern: {pattern}')
    num_files = len(found_files)
    for i, file in enumerate(found_files):
        logger.debug(f'Processing file: {file}')
        # update print statement without newline as a progress indicator including percentage og files processed
        # print(
        #     f'\rProcessing file: <data_folder>{file.replace(data_folder, "")}, Percent done: {100 * i / num_files:0.2f}',
        #     end='')
        df = kraken2_to_dataframe(file, column_names)
        df['file_name'] = os.path.basename(file)
        df_out = pd.concat([df_out, df], axis=0)
    return df_out


def add_pathogens(df: pd.DataFrame, pathogens_file: str):
    """
    Add pathogen information to the DataFrame based on a pathogens reference file.

    Matches rows in the DataFrame with pathogens based on taxonomy ID and updates
    the Priority, Target group, and Priority pathogen group columns.

    Parameters:
        df (pd.DataFrame): The DataFrame to update with pathogen information
        pathogens_file (str): Path to the Excel file containing pathogen reference data

    Returns:
        pd.DataFrame: The updated DataFrame with pathogen information
    """
    merged = df.copy()

    pathogens = read_pathogens(pathogens_file)

    # Use the set_column_dtypes function to convert taxonomy IDs to integers
    pathogens = set_column_dtypes(pathogens, {'TaxonomyID': 'int64'})
    merged = set_column_dtypes(merged, {'NCBI tax ID': 'int64'})

    merged['Priority'] = None
    merged['Target group'] = None
    merged['Priority pathogen group'] = None

    # iterate over the rows in the pathogens dataframe and find the rows in merged with the same value of "NCBI tax ID" as "TaxonomyID"
    # Find the columns in the merged dataframe with values in the group_by_cols list, and group by those columns and merge the values of all columns in the pathogens dataframe
    for _, pathogen_row in pathogens.iterrows():
        # Find the rows in merged with the same TaxonomyID
        subset = merged.loc[merged['NCBI tax ID'] == pathogen_row['TaxonomyID']]
        if len(subset) == 0:
            continue
        subset_scientific_name = subset["Scientific name"].unique()
        logger.debug(
            f'Found {len(subset)} rows with TaxonomyID {pathogen_row["TaxonomyID"]} for pathogen {pathogen_row["scientific name"]}')
        match_row = subset.iloc[0]
        columns_to_compare = get_relevant_columns(match_row.get('Rank code'), RANK_COLUMN_MAPPING)
        mask = create_df_mask_from_column_values(merged, match_row, columns_to_compare)
        num_found = len(merged[mask])
        logger.debug(
            f'Found {num_found} rows in merged dataframe with TaxonomyID {match_row["NCBI tax ID"]} with the rank code {match_row.get("Rank code")}, and relevant columns {columns_to_compare}.')
        merged.loc[mask, 'Type'] = pathogen_row['Type']
        merged.loc[mask, 'Priority'] = pathogen_row['Priority']
        merged.loc[mask, 'Target group'] = pathogen_row['Target group']
        merged.loc[mask, 'Priority pathogen group'] = pathogen_row['Priority pathogen group']
    return merged


def reclassify_salmonella(df: pd.DataFrame) -> pd.DataFrame:
    """Reclassify Salmonella serovar rows by TaxID after add_pathogens().

    PRESERVED FOR FUTURE USE — this function is no longer called (June 2026).
    Previously used when Salmonella Typhi was shown as a separate waterborne
    group. If serovar-level Salmonella reporting is needed again, re-enable by:
      1. Adding TaxID 90370 (Typhi) back to pathogen_group_map.yaml
      2. Un-commenting the call below in main()

    add_pathogens() may assign all S. enterica descendants to 'Salmonella spp.'
    via ancestor lineage matching.  This function corrects two cases:

      - TaxID 90370 (Typhi)       → 'Salmonella Typhi'        (shown under waterborne)
      - TaxID 90371 (Typhimurium) → 'Salmonella Typhimurium'  (kept distinct to prevent
                                     double-counting with TaxID 28901's clade total;
                                     NOT included in any display list)

    TaxID 28901 (S. enterica) rows remain labelled 'Salmonella spp.' and are shown
    under AMR as the total Salmonella burden (clade count, includes all serovars).
    """
    taxid_col = df['NCBI tax ID'].astype(str)
    sal_enterica_mask = df['Priority pathogen group'] == 'Salmonella enterica'
    typhi_mask    = sal_enterica_mask & (taxid_col == '90370')
    typhimur_mask = sal_enterica_mask & (taxid_col == '90371')

    df.loc[typhi_mask,    'Priority pathogen group'] = 'Salmonella Typhi'
    df.loc[typhimur_mask, 'Priority pathogen group'] = 'Salmonella Typhimurium'

    n_typhi    = typhi_mask.sum()
    n_typhimur = typhimur_mask.sum()
    if n_typhi or n_typhimur:
        logger.info(
            f'reclassify_salmonella: {n_typhi} rows → Salmonella Typhi, '
            f'{n_typhimur} rows → Salmonella Typhimurium (not displayed)'
        )
    return df



def filter_and_cast_to_int(filename: str, df: pd.DataFrame, col_name: str):
    """
    Filters DataFrame rows to those that can be converted to int without error.
    Converts the column to int type.
    Prints unique invalid values and does not raise exceptions.
    Parameters:
        filename (str): Name of the file being processed, used for logging
        df (pd.DataFrame): DataFrame to filter and cast
        col_name (str): Column name to process
    Returns:
        pd.DataFrame: Filtered DataFrame with the specified column cast to int
    """
    # Try converting to numeric (NaN if invalid)
    numeric_col = pd.to_numeric(df[col_name], errors='coerce')

    # Mask: keep only values that are not NaN and have no decimal part
    mask_valid = numeric_col.notna() & (numeric_col % 1 == 0)

    # Find unique invalid values
    invalid_values = df.loc[~mask_valid, col_name].unique()
    if len(invalid_values) > 0:
        logger.error(f"Invalid values in {filename} column '{col_name}': {list(invalid_values)}")

    # Filter and cast to int
    df_valid = df.loc[mask_valid].copy()
    df_valid[col_name] = numeric_col[mask_valid].astype(int)

    return df_valid


def read_pathogens_yaml(pathogens_file: str) -> pd.DataFrame:
    """
    Read pathogen group mappings from a YAML (or JSON) config file.

    The file must have a top-level 'pathogens' key containing a list of entries.
    Each entry requires: taxid, pathogen_group.
    Optional fields: scientific_name, type, target_group, priority.

    Returns a DataFrame with the same columns produced by the Excel-based
    read_pathogens() path: TaxonomyID, scientific name, Type, Priority,
    Target group, Priority pathogen group.

    Parameters:
        pathogens_file (str): Path to the YAML or JSON pathogen group map

    Returns:
        pd.DataFrame: DataFrame containing the processed pathogen data
    """
    with open(pathogens_file, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    entries = data.get('pathogens', [])
    if not entries:
        raise ValueError(f"No entries found under 'pathogens' key in {pathogens_file}")
    rows = []
    for entry in entries:
        rows.append({
            'TaxonomyID': entry['taxid'],
            'scientific name': entry.get('scientific_name', ''),
            'Type': entry.get('type', ''),
            'Priority': entry.get('priority', None),
            'Target group': entry.get('target_group', None),
            'Priority pathogen group': entry.get('pathogen_group', None),
        })
    df = pd.DataFrame(rows)
    df = df.dropna(subset=['TaxonomyID'])
    df = filter_and_cast_to_int(pathogens_file, df, col_name='TaxonomyID')
    logger.debug(
        f'Loaded {len(df)} pathogen entries from {pathogens_file}.')
    return df


def read_pathogens(pathogens_file: str) -> pd.DataFrame:
    """
    Read and process the pathogen group map file.

    Accepts either a YAML/JSON config file (recommended, see
    config/pathogen_group_map.yaml) or the legacy Excel file
    (pathogens for database.xlsx) for backward compatibility.

    Parameters:
        pathogens_file (str): Path to the pathogen group map file (.yaml, .yml,
                              .json) or legacy Excel file (.xlsx)

    Returns:
        pd.DataFrame: DataFrame containing the processed pathogen data

    Raises:
        ValueError: If required columns are missing from the pathogen file
    """
    ext = os.path.splitext(pathogens_file)[1].lower()
    if ext in ('.yaml', '.yml', '.json'):
        return read_pathogens_yaml(pathogens_file)

    # ── Legacy Excel path ─────────────────────────────────────────────────────
    pathogens = None
    required_columns = ['domain [bacterial/viral/eukaryotic]', 'Priority', 'Target group', 'Priority pathogen group',
                        'scientific name', 'TaxonomyID']
    sheet_name = "comprehensive_pathogen_list"
    try:
        pathogens = pd.read_excel(
            pathogens_file,
            sheet_name=sheet_name,
            header=2,
            dtype=str
        )
        pathogens = correct_column_names(pathogens, required_columns)
    except ValueError as e:
        logger.error(
            f'Error reading sheet name {sheet_name} from pathogens file: {e}. Trying to find the sheet with "Target group" column.')
    if pathogens is None or not all(col in pathogens.columns for col in required_columns):
        pathogens = find_sheet_with_column(pathogens_file, column="Target group")
        pathogens = correct_column_names(pathogens, required_columns)
    if not all(col in pathogens.columns for col in required_columns):
        raise ValueError(
            f"Pathogens file must contain the following columns: {required_columns}. Found columns: {pathogens.columns.tolist()}")
    logger.debug(
        f'Loaded pathogens with {len(pathogens)} rows from {pathogens_file}. Read columns: {pathogens.columns.tolist()}')
    pathogens = pathogens.dropna(subset=['TaxonomyID'])
    pathogens = filter_and_cast_to_int(pathogens_file, pathogens, col_name="TaxonomyID")

    # rename the "domain [bacterial/viral/eukaryotic]" column to Type
    pathogens.rename(columns={'domain [bacterial/viral/eukaryotic]': 'Type'}, inplace=True)
    return pathogens


def get_base_rank(rank: str) -> str:
    """
    Extract the base rank letter from the rank string, ignoring any numeral suffix.

    Parameters:
        rank (str): The rank value possibly with a numeric suffix.

    Returns:
        str: The base rank letter.
    """
    return ''.join(filter(str.isalpha, rank))


def get_relevant_columns(rank: str, column_mapping: dict) -> list:
    """
    Get the list of columns that should be considered for a given rank.

    Parameters:
        rank (str): The rank value.
        column_mapping (dict): The mapping from rank to column names.

    Returns:
        list: A list of columns up to and including the given rank.
    """
    rank_order = list(column_mapping.keys())
    base_rank = get_base_rank(rank)
    if base_rank in rank_order:
        index = rank_order.index(base_rank)
        return [column_mapping[r] for r in rank_order[:index + 1]]
    return []


def create_df_mask_from_column_values(df: pd.DataFrame, row: pd.Series, columns_to_compare: list[str]) -> pd.Series:
    """
    Creates a boolean mask for a DataFrame that matches rows with the same values
    as a given row for the relevant columns based on the values of the relevant columns.

    Parameters:
        df (pd.DataFrame): The input DataFrame.
        row (pd.Series): The reference row.
        columns_to_compare (list[str]): A list of columns to include in the mask.

    Returns:
        pd.Series: A boolean mask where matching rows are True.
    """
    mask = pd.Series(True, index=df.index)

    for col in columns_to_compare:
        if col in row:
            val = row[col]
            if pd.notnull(val) and str(val).strip() != '':
                mask &= df[col] == val

    return mask


def correct_column_names(df: pd.DataFrame, required_columns: list, threshold: float = 0.8) -> pd.DataFrame:
    """
    Corrects misspelled column names in a dataframe based on fuzzy matching.

    Parameters:
        df (pd.DataFrame): The input dataframe with potentially misspelled column names.
        required_columns (list): List of required (correct) column names.
        threshold (float): Similarity threshold for fuzzy matching (0 to 1). Default is 0.8.

    Returns:
        pd.DataFrame: DataFrame with corrected column names where applicable.

    Raises:
        ValueError: If a required column is missing and no close match is found.
    """
    corrected_columns = df.columns.to_list()
    existing_columns = set(df.columns)

    for correct_col in required_columns:
        if correct_col not in existing_columns:
            # Try to find a close match
            close_matches = get_close_matches(correct_col, df.columns, n=1, cutoff=threshold)
            if close_matches:
                matched_col = close_matches[0]
                logger.debug(f"Renaming column: '{matched_col}' → '{correct_col}'")
                col_index = corrected_columns.index(matched_col)
                corrected_columns[col_index] = correct_col
            else:
                raise ValueError(
                    f"Column '{correct_col}' is missing and no close match was found in dataframe columns: {list(df.columns)}"
                )

    df.columns = corrected_columns
    return df


def find_sheet_with_column(file_path: str, column: str) -> pd.DataFrame:
    """
    Find the first sheet in an Excel file that contains a specific column.

    Parameters:
        file_path (str): Path to the Excel file
        column (str): Column name to search for (case-insensitive)

    Returns:
        pd.DataFrame: DataFrame from the first sheet that contains the specified column

    Raises:
        ValueError: If no sheet is found containing the specified column
    """
    low_column = column.lower()
    # Load all sheets
    xls = pd.ExcelFile(file_path)

    for sheet_name in xls.sheet_names:
        # Read the sheet without headers
        df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        for idx, row in df_raw.iterrows():
            values = [str(val).strip().lower() for val in row.values]
            if low_column in values:
                # Found the header row; read the actual DataFrame from here
                df = pd.read_excel(xls, sheet_name=sheet_name, header=idx)
                return df

    raise ValueError(f"'{column}' column not found in any sheet.")


def main():
    kraken2_column_names = ['Pct. of Frags', 'No of Frags root', 'No of Frags', 'Rank code', 'NCBI tax ID',
                            'Scientific name']
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path', help='Path to root of kraken2 files', type=str, required=True)
    parser.add_argument('--metadata_file', help='Path to metadata file', type=str, required=True)
    _default_pathogens = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'pathogen_group_map.yaml')
    )
    parser.add_argument('--pathogens_file',
                        help='Path to pathogen group map file (.yaml/.yml/.json) or legacy Excel file (.xlsx). '
                             f'Defaults to pipeline_scripts/config/pathogen_group_map.yaml',
                        type=str, required=False, default=_default_pathogens)
    parser.add_argument('--feather_output_path', help='Path to output directory for feather files', type=str,
                        required=True)
    parser.add_argument('--xlsx_output_path', help='Path to output directory for xlsx files', type=str,
                        required=False, default=None)
    parser.add_argument('--column_names',
                        help=f'Names of columns in kraken2.report.tx files, default: {kraken2_column_names}',
                        type=str, required=False, default=','.join(kraken2_column_names))
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing output files instead of merging with them')
    parser.add_argument('--suffix', help='Suffix of kraken2 files to include', type=str, required=False,
                        default='kraken2.report.txt')
    parser.add_argument('--split_by',
                        help='Metadata column to split and name datasets by, e.g. country or site_id, default country',
                        type=str, required=False,
                        default='country')
    args = parser.parse_args()

    if not os.path.exists(args.data_path):
        logger.error(f'Data path does not exist: {args.data_path}')
        sys.exit(1)
    if not os.path.exists(args.metadata_file):
        logger.error(f'Metadata file does not exist: {args.metadata_file}')
        sys.exit(1)
    if not os.path.exists(args.pathogens_file):
        logger.error(f'Pathogens for database file does not exist: {args.pathogens_file}')
        sys.exit(1)
    # Ensure output directories exists
    os.makedirs(args.feather_output_path, exist_ok=True)
    if args.xlsx_output_path:
        os.makedirs(args.xlsx_output_path, exist_ok=True)

    column_names = args.column_names.lstrip('[').rstrip(']').split(',')
    df, run_accessions = create_kraken_dataset_from_metadata(args.metadata_file, args.data_path, column_names,
                                                             args.suffix)
    if df.empty:
        logger.error('No kraken2 reports found in the metadata file or data folder.')
        sys.exit(1)
    df = add_pathogens(df, args.pathogens_file)
    # reclassify_salmonella(df)  # PRESERVED: re-enable for serovar-level Salmonella split
    df = set_column_dtypes(df, {
        'Pct. of Frags': 'float64',
        'No of Frags root': 'int64',
        'No of Frags': 'int64',
        'NCBI tax ID': 'str',
        'protocol_id': 'str',
        'sampling_date': 'datetime64[ns]',  # Ensure sampling_date is in datetime format
        'lon': 'float64',
        'lat': 'float64'
    })

    if df.empty:
        logger.error('No kraken2 reports found in the metadata file or data folder.')
        sys.exit(1)
    try:
        df = df.sort_values(
            by=['sampling_site_id', 'sample_id', 'sampling_date', 'Priority pathogen group', 'Target group'],
            ascending=True)
        df = df.reset_index(drop=True)
    except KeyError as e:
        logger.error(f'Error sorting DataFrame: {e}. Proceeding without sorting.')
    split_by = args.split_by
    subsets = split_dataset(df, split_by)
    if not subsets:
        logger.error(f'No data to save after splitting by {split_by}. Exiting.')
        sys.exit(1)
    # Merge with existing data (skipped when --overwrite is set)
    if args.overwrite:
        logger.info('--overwrite set: skipping merge with existing files, writing fresh datasets')
        merged_subsets = subsets
    else:
        merged_subsets = merge_datasets_with_existing(subsets, run_accessions, args.feather_output_path)
    save_subsets(merged_subsets, args.feather_output_path, FEATHER_TYPE)
    if args.xlsx_output_path:
        save_subsets(merged_subsets, args.xlsx_output_path, XLSX_TYPE)
    # Create datasets with "Target group" values
    target_groups = create_target_groups(merged_subsets)
    save_subsets(target_groups, args.feather_output_path, FEATHER_TYPE)
    if args.xlsx_output_path:
        save_subsets(target_groups, args.xlsx_output_path, XLSX_TYPE)


if __name__ == '__main__':
    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)],
                        format='%(levelname)-6s: "%(message)s" ( function=%(funcName)s() Line %(lineno)-4d)',
                        encoding='utf-8', level='INFO')
    main()
