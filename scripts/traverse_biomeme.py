import os
import warnings
from typing import Dict, List, Tuple, Optional, Any, Union
from pathlib import Path
from argparse import ArgumentParser

import pandas as pd
from pandas import DataFrame
from tabulate import tabulate

# Ignore specific pandas warnings
warnings.filterwarnings('ignore', message='Data Validation extension is not supported and will be removed')

class ODINProcessTraverser:
    def __init__(self, data_root: str, metadata_master: str, method: str = "biomeme", verbose: bool = False):
        """
        Initialize the BiomemeTraverser class

        Args:
            data_root: Path to the data root directory
            metadata_master: Name of the metadata excel file
            method: The analysis method (default: "biomeme")
            verbose: Whether to display detailed information (default: False)
        """
        self.data_root = data_root
        self.metadata_master = metadata_master
        self.metadata_dfs: Optional[Dict[str, DataFrame]] = None
        self.method = method
        self.verbose = verbose

    def get_site_metadata(self, sites_df: DataFrame, site_ID: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[float], Optional[float]]:
        """
        Look up site metadata for a given site_ID from the sites DataFrame.

        Args:
            sites_df: DataFrame from the "sites" tab of metadata
            site_ID: Site ID to look up

        Returns:
            Tuple: (site, site_ID, location, city, country, sample_type, longitude, latitude)
        """
        try:
            if 'site_ID' not in sites_df.columns:
                print("site_ID column not found in sites metadata")
                return None, None, None, None, None, None, None, None

            site_row = sites_df[sites_df['site_ID'] == site_ID]
            if site_row.empty:
                print(f"Site_ID '{site_ID}' not found in sites metadata")
                return None, None, None, None, None, None, None, None

            site = str(site_row['site'].iloc[0]) if 'site' in site_row.columns else None
            location = str(site_row['location'].iloc[0]) if 'location' in site_row.columns else None
            city = str(site_row['city'].iloc[0]) if 'city' in site_row.columns else None
            country = str(site_row['country'].iloc[0]) if 'country' in site_row.columns else None
            sample_type = str(site_row['sample_type'].iloc[0]) if 'sample_type' in site_row.columns else None
            longitude = float(site_row['longitude'].iloc[0]) if 'longitude' in site_row.columns else None
            latitude = float(site_row['latitude'].iloc[0]) if 'latitude' in site_row.columns else None

            return site, site_ID, location, city, country, sample_type, longitude, latitude
        except Exception as e:
            print(f"Error looking up site metadata: {e}")
            return None, None, None, None, None, None, None, None

    def load_metadata(self) -> bool:
        """
        Load metadata from Excel file into class attribute

        Returns:
            True if successful, False otherwise
        """
        try:
            self.metadata_dfs = self.read_metadata_excel()
            return self.metadata_dfs is not None
        except Exception as e:
            print(f"Error loading metadata: {e}")
            return False

    def process_metadata(self, sites_df: DataFrame, biomeme_df: DataFrame) -> pd.DataFrame:
        """
        For each row in biomeme_df, add metadata columns by matching sample_code with site_ID in samples tab,
        then looking up location info in sites tab and city name in lookup_tables.

        Args:
            sites_df: DataFrame from "sites" tab
            biomeme_df: DataFrame from "biomeme" tab

        Returns:
            biomeme_df with added metadata columns
        """
        samples_df = self.metadata_dfs.get("samples")
        lookup_tables_df = self.metadata_dfs.get("lookup_tables")
        if samples_df is None or "sample_code" not in samples_df.columns or "site_ID" not in samples_df.columns:
            print("Samples tab missing or missing required columns")
            return biomeme_df

        # Prepare columns for metadata
        biomeme_df = biomeme_df.copy()
        biomeme_df['site'] = None
        biomeme_df['site_ID'] = None
        biomeme_df['location'] = None
        biomeme_df['longitude'] = None
        biomeme_df['latitude'] = None
        biomeme_df['city'] = None
        biomeme_df['country'] = None
        biomeme_df['sample_type'] = None
        biomeme_df['country_code'] = None
        biomeme_df['partner_sample_code'] = None

        for idx, biomeme_row in biomeme_df.iterrows():
            sample_code = biomeme_row.get('sample_code', None)
            if sample_code is None:
                continue
            sample_row = samples_df[samples_df['sample_code'] == sample_code]
            if sample_row.empty:
                continue
            site_id = sample_row['site_ID'].iloc[0]
            # --- Get all site metadata ---
            site, site_ID, location, city, country, sample_type, longitude, latitude = self.get_site_metadata(sites_df, site_id)
            biomeme_df.at[idx, 'site'] = site
            biomeme_df.at[idx, 'site_ID'] = site_ID
            biomeme_df.at[idx, 'location'] = location
            biomeme_df.at[idx, 'longitude'] = longitude
            biomeme_df.at[idx, 'latitude'] = latitude
            biomeme_df.at[idx, 'city'] = city
            biomeme_df.at[idx, 'country'] = country
            biomeme_df.at[idx, 'sample_type'] = sample_type
            # --- country_code from site_row ---
            site_row = sites_df[sites_df['site_ID'] == site_id]
            country_code = site_row['country_code'].iloc[0] if not site_row.empty and 'country_code' in site_row.columns else None
            biomeme_df.at[idx, 'country_code'] = country_code
            # --- partner_sample_code from samples tab ---
            partner_sample_code = sample_row['partner_sample_code'].iloc[0] if 'partner_sample_code' in sample_row.columns else None
            biomeme_df.at[idx, 'partner_sample_code'] = partner_sample_code

        return biomeme_df

    def read_metadata_excel(self) -> Optional[Dict[str, DataFrame]]:
        """
        Read each worksheet of the metadata excel file into separate DataFrames,
        skipping specific lines for each worksheet

        Returns:
            Dictionary with worksheet names as keys and corresponding DataFrames as values,
            or None if an error occurs
        """
        try:
            # Type check inputs
            if not isinstance(self.data_root, str):
                raise TypeError(f"data_root must be a string, got {type(self.data_root)}")
            if not isinstance(self.metadata_master, str):
                raise TypeError(f"metadata_master must be a string, got {type(self.metadata_master)}")

            # Construct the file path using the class attributes
            file_path = os.path.join(self.data_root, self.metadata_master)

            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Excel file not found at path: {file_path}")

            # Read all sheets into a dictionary of DataFrames
            excel_file = pd.ExcelFile(file_path)
            sheet_names: List[str] = excel_file.sheet_names

            # Dictionary to store all DataFrames
            dfs: Dict[str, DataFrame] = {}

            for sheet in sheet_names:
                # Define skiprows based on the worksheet name
                if sheet.lower() == "sites":
                    skiprows = [1]  # Skip second line
                elif sheet.lower() in ["samples", "nanopore", "biomeme"]:
                    skiprows = [1] if sheet.lower() == "samples" else [0, 2]
                else:
                    skiprows = None

                # Unified reading and processing for sheets with sampling_date
                if sheet.lower() in ["samples", "biomeme", "nanopore"]:
                    df = pd.read_excel(
                        excel_file,
                        sheet_name=sheet,
                        skiprows=skiprows,
                        dtype={'sampling_date': str}
                    )
                    if 'sampling_date' in df.columns:
                        df['sampling_date'] = pd.to_datetime(df['sampling_date'], format='%Y%m%d', errors='coerce')
                    # Additional filtering for samples sheet
                    if sheet.lower() == "samples" and 'site_ID' in df.columns:
                        df = df[df['site_ID'].notna()]
                else:
                    df = pd.read_excel(excel_file, sheet_name=sheet, skiprows=skiprows)
                # Remove rows where all columns are NaN/NaT
                df = df.dropna(how='all')

                if not isinstance(df, DataFrame):
                    raise TypeError(f"Expected DataFrame for sheet {sheet}, got {type(df)}")

                dfs[sheet] = df

                # # Print information about each worksheet
                # print(f"\nWorksheet: {sheet}")
                # print(f"Number of rows: {len(df)}")
                # print(f"Number of columns: {len(df.columns)}")
                # print("Columns:")
                # for col in df.columns:
                #     print(f"- {col}")

            return dfs

        except Exception as e:
            print(f"Error occurred while reading the excel file: {e}")
            return None


    def scan_curated_path(self, curated_dir: str) -> List[str]:
        """
        Scan the curated_path directory and return a list of files

        Args:
            curated_dir: Path to the curated directory

        Returns:
            List of files found in the curated_path directory
        """
        files_list: List[str] = []
        print("Scanning curated_path directory...")

        try:
            # Type check input
            if not isinstance(curated_dir, str):
                raise TypeError(f"curated_dir must be a string, got {type(curated_dir)}")

            # Check if directory exists
            if not os.path.exists(curated_dir):
                print(f"Directory '{curated_dir}' does not exist!")
                return files_list

            if not os.path.isdir(curated_dir):
                raise NotADirectoryError(f"Path is not a directory: {curated_dir}")

            # Walk through the curated_path directory
            for root, dirs, files in os.walk(curated_dir):
                for file in files:
                    # Get the full file path relative to curated_path
                    rel_path = os.path.relpath(os.path.join(root, file), curated_dir)
                    files_list.append(rel_path)

            return files_list

        except Exception as e:
            print(f"Error occurred: {e}")
            return files_list


    def traverse_directory(self, path: Optional[Union[str, Path]] = None) -> Dict[str, Dict[str, List[str]]]:
        """
        Walk through biomeme_input_data directory and collect biomeme data files grouped by country_code and sampling_date.

        Args:
            path: The starting directory path (defaults to DATA_ROOT/biomeme_input_data if None)

        Returns:
            Dictionary: {country_code: {sampling_date: [list of files in that folder]}}
        """
        raw_data: Dict[str, Dict[str, List[str]]] = {}

        try:
            base_path = os.path.join(self.data_root, "biomeme_input_data")
            if path is not None:
                base_path = path if isinstance(path, str) else str(path)

            if not os.path.exists(base_path):
                raise FileNotFoundError(f"Directory does not exist: {base_path}")

            if not os.path.isdir(base_path):
                raise NotADirectoryError(f"Path is not a directory: {base_path}")

            # Top-level: country_code
            with os.scandir(base_path) as country_entries:
                for country_entry in country_entries:
                    if country_entry.is_dir(follow_symlinks=False):
                        country_code = country_entry.name
                        country_dict: Dict[str, List[str]] = {}
                        # Next level: sampling_date
                        with os.scandir(country_entry.path) as date_entries:
                            for date_entry in date_entries:
                                if date_entry.is_dir(follow_symlinks=False):
                                    sampling_date = date_entry.name
                                    files = []
                                    for file_entry in os.scandir(date_entry.path):
                                        if file_entry.is_file():
                                            files.append(file_entry.name)
                                    country_dict[sampling_date] = files
                        raw_data[country_code] = country_dict

        except Exception as e:
            print(f"Error occurred: {e}")
            return raw_data

        return raw_data

    def run(self) -> Optional[Dict[str, Dict[str, List[str]]]]:
        """
        Execute the complete analysis process: load metadata, traverse directory,
        and process metadata for sites.

        Returns:
            Dictionary containing country_code and sampling_date information with added metadata, or None if error occurs
        """
        try:
            if not self.load_metadata():
                raise ValueError("Failed to read metadata excel file")

            country_sampling_dates = self.traverse_directory()
            if not country_sampling_dates:
                attempted_path = os.path.join(self.data_root, "biomeme_input_data")
                print(f"No country_codes found or error occurred during directory traversal.\n"
                      f"Tried to look in: {attempted_path}\n"
                      f"Directory exists: {os.path.exists(attempted_path)}\n"
                      f"Is directory: {os.path.isdir(attempted_path)}")
                return None

            # Ensure both "sites" and "biomeme" tabs are present
            if "sites" not in self.metadata_dfs or "biomeme" not in self.metadata_dfs:
                print("Required worksheets not found in metadata file")
                return None

            # Add metadata to biomeme_df, not sites
            biomeme_df_with_meta = self.process_metadata(self.metadata_dfs["sites"], self.metadata_dfs["biomeme"])
            self.metadata_dfs["biomeme"] = biomeme_df_with_meta
            return country_sampling_dates

        except Exception as e:
            print(f"Error in main execution: {e}")
            return None


# Example usage
if __name__ == "__main__":
    import sys
    from scripts.decode import extract_edna
    import pandas as pd
    from tabulate import tabulate

    parser = ArgumentParser(description="ODIN Data Processing Tool")
    parser.add_argument('--data-root', type=str, required=True, help='Path to the data root directory')
    parser.add_argument('--metadata-master', type=str, required=True, help='Relative path and filename of the metadata Excel file (e.g. "data/metadata_test_environment.xlsx")')
    parser.add_argument('--enlighten-data-path', type=str, required=True, help='Path to Enlighten visualization data output directory')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    args, _ = parser.parse_known_args()

    DATA_ROOT = args.data_root
    METADATA_MASTER = args.metadata_master
    ENLIGHTEN_DATA_PATH = args.enlighten_data_path

    # Master join for biomeme input data path
    BIOMEME_INPUT_PATH = os.path.join(DATA_ROOT, "biomeme_input_data")

    try:
        # Create traverser instance
        traverser = ODINProcessTraverser(DATA_ROOT, METADATA_MASTER, method='biomeme', verbose=args.verbose)

        # Run the complete analysis
        country_sampling_dates = traverser.run()

        # Flatten the nested dictionary for DataFrame creation
        if country_sampling_dates:
            expanded_data = []
            for country_code, sampling_dates_dict in country_sampling_dates.items():
                for sampling_date, files_list in sampling_dates_dict.items():
                    if not files_list or len(files_list) == 0:
                        expanded_data.append({
                            'country_code': country_code,
                            'sampling_date': sampling_date,
                            'file_name': None
                        })
                    else:
                        for file_name in files_list:
                            expanded_data.append({
                                'country_code': country_code,
                                'sampling_date': sampling_date,
                                'file_name': file_name
                            })

            expanded_df = pd.DataFrame(expanded_data)

            if expanded_df is None:
                sys.exit(1)

            biomeme_metadata_df = traverser.metadata_dfs["biomeme"] if traverser.metadata_dfs and "biomeme" in traverser.metadata_dfs else None
            all_results = []  # Collect all result_df here
            for idx, row in expanded_df.iterrows():
                country_code = row.get('country_code', None)
                sampling_date = row.get('sampling_date', None)
                file_name = row.get('file_name', None)
                if country_code and sampling_date and not isinstance(file_name, str):
                    print(f"[traverse_biomeme] Skipping empty folder: {os.path.join(BIOMEME_INPUT_PATH, str(country_code), str(sampling_date))} — no files found. Check if data files are missing or misplaced.")
                    continue
                if country_code and sampling_date and isinstance(file_name, str) and file_name.endswith('.xlsx') and file_name != 'metadata.xlsx':
                    excel_file_path = os.path.join(BIOMEME_INPUT_PATH, str(country_code), str(sampling_date), file_name)
                    try:
                        # Pass biomeme metadata_df and row metadata
                        result_df = extract_edna(excel_file_path, metadata_df=biomeme_metadata_df, row_metadata=row.to_dict())
                        # --- Verify country_code in biomeme_metadata_df for this file ---
                        if biomeme_metadata_df is not None and 'country_code' in biomeme_metadata_df.columns and 'biomeme_run_name' in biomeme_metadata_df.columns:
                            file_rows = result_df
                            for meta_idx, meta_row in file_rows.iterrows():
                                meta_country_code = meta_row.get('country_code', None)
                                if meta_country_code is not None and str(meta_country_code) != str(country_code):
                                    print(
                                        f"Country code mismatch for file '{file_name}' found in folder '{country_code}'. "
                                        f"Metadata country_code: '{meta_country_code}', folder country_code: '{country_code}'"
                                        f"Hint: Check the metadata file '{METADATA_MASTER}' for consistency. Check if the country_code in the metadata matches the folder structure for the biomeme result file."
                                    )
                                    sys.exit(1)
                        print(f"Processed {excel_file_path}:")
                        # print(tabulate(result_df, headers='keys', tablefmt='psql', showindex=False))
                        all_results.append(result_df)
                    except Exception as e:
                        print(f"Error processing {excel_file_path}: {e}")

            # Aggregate all result_df into a single DataFrame
            if all_results:
                all_results_df = pd.concat(all_results, ignore_index=True)

                # print("\nAggregated Results:")
                # print(tabulate(all_results_df, headers='keys', tablefmt='psql', showindex=False))

                # Remove timezone info from all relevant datetime columns before writing to Excel
                for col in ['sampling_date', 'run_date', 'Date', 'Assay Date']:
                    if col in all_results_df.columns:
                        if pd.api.types.is_datetime64_any_dtype(all_results_df[col]):
                            all_results_df[col] = all_results_df[col].dt.tz_localize(None)
                        elif all_results_df[col].dtype == "object":
                            all_results_df[col] = all_results_df[col].apply(
                                lambda x: x.tz_localize(None) if (hasattr(x, "tz_localize")) else x
                            )

                # Write out as "BiomemeAssay.xlsx" and "BiomemeAssay.feather"
                excel_output_dir = os.path.join(DATA_ROOT, "biomeme_processed")
                os.makedirs(excel_output_dir, exist_ok=True)
                all_results_df.to_excel(os.path.join(excel_output_dir, "BiomemeAssay.xlsx"), index=False)

                feather_output_dir = ENLIGHTEN_DATA_PATH
                os.makedirs(feather_output_dir, exist_ok=True)
                all_results_df.to_feather(os.path.join(feather_output_dir, "BiomemeAssay.feather"))

                # Log where the results are written to
                print(f"BiomemeAssay.xlsx written to {excel_output_dir}")
                print(f"BiomemeAssay.feather written to {feather_output_dir}")


    except Exception as e:
        print(f"Error in main execution: {e}")
        sys.exit(1)