import os
import re
import sys
import argparse
import logging
import warnings

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    GREY = '\033[90m'

REQUIREMENTS_FILE = os.path.join(os.path.dirname(__file__), '../requirements.txt')

# Map PyPI package names to import names if they differ
PKG_IMPORT_MAP = {
    'odfpy': 'odf',
    'pytest-cov': 'pytest'
    # Add more mappings as needed
}

def get_required_packages():
    pkgs = []
    if os.path.exists(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Remove version specifiers (e.g. pandas>=1.0)
                pkg = re.split(r'[<>=]', line)[0].strip()
                if pkg:
                    pkgs.append(pkg)
    return pkgs

LOG_FILENAME = os.path.join(os.path.dirname(__file__), 'integrity_check.log')
file_handler = logging.FileHandler(LOG_FILENAME, mode='a', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[file_handler])
logger = logging.getLogger('integrity_check')

def write_output(message, verbose, force_console=False):
    logger.info(message)  # Always log everything
    if force_console or verbose:
        print(message)

def check_packages():
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}PYTHON PACKAGE CHECK{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=True, force_console=True)
    pkgs = get_required_packages()
    missing = []
    for pkg in pkgs:
        import_name = PKG_IMPORT_MAP.get(pkg, pkg)
        try:
            __import__(import_name)
            write_output(f"  {Colors.OKGREEN}[OK]{Colors.ENDC} {pkg}", verbose=True, force_console=True)
        except ImportError:
            # Try some common fallback import names
            fallback_names = set()
            fallback_names.add(pkg.lower())
            fallback_names.add(pkg.replace('-', '_'))
            fallback_names.add(pkg.replace('_', '-'))
            if '-' in pkg:
                fallback_names.add(pkg.split('-')[0])
            if '_' in pkg:
                fallback_names.add(pkg.split('_')[0])
            fallback_names.discard(import_name)
            found = False
            for fallback in fallback_names:
                try:
                    __import__(fallback)
                    write_output(f"  {Colors.WARNING}[WARNING]{Colors.ENDC} The package '{pkg}' is installed but import name is likely '{fallback}'.\n           Please add '{pkg}': '{fallback}' to PKG_IMPORT_MAP in integrity_check.py.", verbose=True, force_console=True)
                    found = True
                    break
                except ImportError:
                    continue
            if not found:
                write_output(f"  {Colors.FAIL}[MISSING]{Colors.ENDC} {pkg}", verbose=True, force_console=True)
                missing.append(pkg)
    if missing:
        venv_path = os.environ.get('ODIN_VENV_PATH') or '/path/to/venv'
        project_root = os.environ.get('ODIN_PROJECT_ROOT') or '/path/to/project/root'
        write_output(f"\n{Colors.WARNING}Did you run 'pip install -r requirements.txt' in your virtual environment?{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"{Colors.WARNING}Steps to update your virtual environment and install required packages:\n\n. {venv_path}/bin/activate\ncd {project_root}\npip install -r requirements.txt\n\nFor more details, see the setup guide:\n  pdf-doc/setup_mobile_lab_computer.pdf{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"{Colors.FAIL}Aborting integrity check due to missing Python packages.{Colors.ENDC}", verbose=True, force_console=True)
        sys.exit(1)
    write_output(f"{Colors.OKCYAN}PYTHON PACKAGE CHECK complete.{Colors.ENDC}", verbose=True, force_console=True)

# Run package check before any third-party or custom imports
check_packages()

# Now safe to import third-party and custom modules
import pandas as pd
import time
from traverse_biomeme import ODINProcessTraverser

# Suppress openpyxl UserWarnings (e.g. Data Validation extension warnings)
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Variable mapping: (override_name, default_name)
VAR_MAP = [
    ("minknow_data_dir", "DEFAULT_MINKNOW_DATA_DIR"),
    ("databases_file", "DEFAULT_DATABASES_FILE"),
    ("venv_folder", "DEFAULT_VENV_DIR"),
    ("output_dir", "DEFAULT_OUTPUT_DIR"),
    ("metadata_file", "DEFAULT_METADATA_FILE"),
    ("enlighten_data_path", "DEFAULT_ENLIGHTEN_DATA_PATH"),
    ("taxprofiler_dir", "DEFAULT_TAXPROFILER_PATH"),
    ("biomeme_data_path", "DEFAULT_BIOMEME_DATA_PATH"),
    ("pathogens_file", "DEFAULT_PATHOGENS_FILE"),
    ("xlsx_data_path", "DEFAULT_XLSX_DATA_PATH"),
]

def get_biomeme_file_structure(path, level=0, verbose=False):
    """Recursively get the structure of biomeme files for reporting."""
    if not os.path.isdir(path):
        return
    indent = '  ' * level
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            write_output(f"{indent}- {Colors.BOLD}{item}{Colors.ENDC}/", verbose)
            get_biomeme_file_structure(item_path, level + 1, verbose)
        else:
            write_output(f"{indent}  - {Colors.GREY}{item}{Colors.ENDC}", verbose)

def find_biomeme_files(env, verbose=False):
    biomeme_data_path = env.get('biomeme_data_path') or env.get('DEFAULT_BIOMEME_DATA_PATH')
    if not biomeme_data_path:
        write_output(f"  {Colors.FAIL}[MISSING]{Colors.ENDC} biomeme_data_path not set.", verbose)
        return None
    biomeme_input_path = os.path.join(biomeme_data_path, "biomeme_input_data")
    traverser = ODINProcessTraverser(biomeme_data_path, '', method='biomeme', verbose=False)
    files_dict = traverser.traverse_directory(biomeme_input_path)
    if not files_dict:
        write_output(f"  {Colors.WARNING}[NOT FOUND]{Colors.ENDC} No biomeme files found in {biomeme_input_path}", verbose)
        return None
    return files_dict

def check_paths(env):
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}PATH CHECKS{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=True, force_console=True)
    for override, default in VAR_MAP:
        value = env.get(override) or env.get(default)
        used = override if env.get(override) else default
        if not value:
            write_output(f"  {Colors.FAIL}[MISSING]{Colors.ENDC} {override} / {default} not set.", verbose=True, force_console=True)
            continue
        # Expand environment variables and user
        path_expanded = os.path.expandvars(os.path.expanduser(value))
        if os.path.exists(path_expanded):
            write_output(f"  {Colors.OKGREEN}[OK]{Colors.ENDC} {used}: {path_expanded}", verbose=True, force_console=True)
        else:
            write_output(f"  {Colors.WARNING}[NOT FOUND]{Colors.ENDC} {used}: {path_expanded}", verbose=True, force_console=True)
    write_output(f"{Colors.OKCYAN}PATH CHECKS complete.{Colors.ENDC}", verbose=True, force_console=True)

def check_specific_files(env):
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}FILE EXISTENCE CHECKS{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=True, force_console=True)
    write_output(f"{Colors.OKCYAN}Checking for required files: databases, metadata, pathogens{Colors.ENDC}", verbose=True, force_console=True)
    files_to_check = {
        'databases': env.get('databases_file') or env.get('DEFAULT_DATABASES_FILE'),
        'metadata': env.get('metadata_file') or env.get('DEFAULT_METADATA_FILE'),
        'pathogens': env.get('pathogens_file') or env.get('DEFAULT_PATHOGENS_FILE'),
    }
    for label, path in files_to_check.items():
        if not path:
            write_output(f"  {Colors.FAIL}[MISSING]{Colors.ENDC} {label} file path not set.", verbose=True, force_console=True)
            continue
        path_expanded = os.path.expandvars(os.path.expanduser(path))
        if os.path.isfile(path_expanded):
            write_output(f"  {Colors.OKGREEN}[OK]{Colors.ENDC} {label}: {path_expanded}", verbose=True, force_console=True)
        else:
            write_output(f"  {Colors.WARNING}[NOT FOUND]{Colors.ENDC} {label}: {path_expanded}", verbose=True, force_console=True)
    write_output(f"{Colors.OKCYAN}FILE EXISTENCE CHECKS complete.{Colors.ENDC}", verbose=True, force_console=True)

def check_nanopore_metadata_structure(env, silent=False):
    errors = []
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}NANOPORE METADATA STRUCTURE CHECK{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=not silent)
    write_output(f"  {Colors.OKCYAN}Loading metadata file...{Colors.ENDC}", verbose=not silent)
    metadata_path = env.get('metadata_file') or env.get('DEFAULT_METADATA_FILE')
    miniknow_data_dir = env.get('minknow_data_dir') or env.get('DEFAULT_MINKNOW_DATA_DIR')
    if not metadata_path or not miniknow_data_dir:
        errors.append("Missing metadata_file or minknow_data_dir config.")
        write_output(f"  {Colors.WARNING}[SKIP]{Colors.ENDC} Missing metadata_file or minknow_data_dir config.", verbose=not silent)
        return errors
    metadata_path = os.path.expandvars(os.path.expanduser(metadata_path))
    miniknow_data_dir = os.path.expandvars(os.path.expanduser(miniknow_data_dir))
    if not os.path.isfile(metadata_path):
        errors.append(f"Metadata file not found: {metadata_path}")
        write_output(f"  {Colors.FAIL}[NOT FOUND]{Colors.ENDC} Metadata file: {metadata_path}", verbose=not silent)
        return errors
    try:
        write_output(f"  {Colors.OKCYAN}Sheet names in metadata file: {pd.ExcelFile(metadata_path).sheet_names}{Colors.ENDC}", verbose=not silent)
        xls = pd.ExcelFile(metadata_path)
        nanopore_sheet = None
        for sheet in xls.sheet_names:
            if 'nanopore' in sheet.lower():
                nanopore_sheet = sheet
                break
        if not nanopore_sheet:
            errors.append("No 'nanopore' sheet found in metadata file.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'nanopore' sheet found in metadata file.", verbose=not silent)
            return errors
        write_output(f"  {Colors.OKCYAN}Loading nanopore tab...{Colors.ENDC}", verbose=not silent)
        start_time = time.time()
        try:
            df = pd.read_excel(xls, sheet_name=nanopore_sheet, header=1)
        except Exception as e:
            errors.append(f"Failed to read nanopore tab: {e}")
            write_output(f"  {Colors.WARNING}[WARN]{Colors.ENDC} Failed to read nanopore tab: {e}", verbose=not silent)
            return errors
        end_time = time.time()
        write_output(f"  {Colors.OKCYAN}Elapsed time for reading nanopore tab: {end_time-start_time:.2f} seconds{Colors.ENDC}", verbose=not silent)
        col_map = {}
        barcode_col = None
        sample_code_col = None
        for col in df.columns:
            col_lc = col.lower()
            if 'runname' in col_lc:
                col_map['runName'] = col
            elif 'samplename' in col_lc:
                col_map['sampleName'] = col
            elif 'accession' in col_lc:
                col_map['run_accession'] = col
            elif 'barcode' == col_lc:
                barcode_col = col
            elif 'sample_code' == col_lc:
                sample_code_col = col
        missing_cols = [k for k in ['run_accession', 'sample_code'] if k not in col_map and (k != 'sample_code' or not sample_code_col)]
        if missing_cols:
            errors.append(f"Missing columns in nanopore sheet: {', '.join(missing_cols)}")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} Missing columns in nanopore sheet: {', '.join(missing_cols)}", verbose=not silent)
            return errors
        if not barcode_col:
            errors.append("No 'barcode' column found in nanopore sheet.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'barcode' column found in nanopore sheet.", verbose=not silent)
            return errors
        samples_sheet = None
        for sheet in xls.sheet_names:
            if 'samples' == sheet.lower():
                samples_sheet = sheet
                break
        if not samples_sheet:
            errors.append("No 'samples' sheet found in metadata file.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'samples' sheet found in metadata file.", verbose=not silent)
            return errors
        write_output(f"  {Colors.OKCYAN}Loading samples tab...{Colors.ENDC}", verbose=not silent)
        df_samples = pd.read_excel(xls, sheet_name=samples_sheet, header=1)
        samples_code_col = None
        for col in df_samples.columns:
            if 'filled out automatically' in col.lower():
                samples_code_col = col
                break
        if not samples_code_col:
            errors.append("No sample_code column found in samples sheet.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No sample_code column found in samples sheet.", verbose=not silent)
            return errors
        write_output(f"  {Colors.OKCYAN}Comparing sample codes...{Colors.ENDC}", verbose=not silent)
        nanopore_sample_codes = set()
        nanopore_code_rows = {}
        for idx, row in df.iloc[1:].iterrows():
            code = str(row[sample_code_col]).strip() if sample_code_col else ''
            if code and code.lower() != 'nan':
                nanopore_sample_codes.add(code)
                nanopore_code_rows[code] = idx + 2
        samples_sample_codes = set(str(val).strip() for i, val in enumerate(df_samples[samples_code_col]) if i != 1 and str(val).strip() and str(val).strip().lower() != 'nan')
        missing_in_samples = sorted([code for code in nanopore_sample_codes if code not in samples_sample_codes])
        unused_in_nanopore = sorted([code for code in samples_sample_codes if code not in nanopore_sample_codes])
        if missing_in_samples:
            errors.append(f"Sample codes in nanopore tab NOT found in samples tab: {missing_in_samples}")
            write_output(f"\n{Colors.FAIL}Sample codes in nanopore tab NOT found in samples tab:{Colors.ENDC}", verbose=not silent)
            for code in missing_in_samples:
                rownum = nanopore_code_rows.get(code, '?')
                write_output(f"  {Colors.FAIL}{code}{Colors.ENDC} (row {rownum})", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All sample codes in nanopore tab are valid (found in samples tab).{Colors.ENDC}", verbose=not silent)
        if unused_in_nanopore:
            errors.append(f"Sample codes in samples tab NOT used in nanopore tab: {unused_in_nanopore}")
            write_output(f"\n{Colors.WARNING}Sample codes in samples tab NOT used in nanopore tab (low severity):{Colors.ENDC}", verbose=not silent)
            for code in unused_in_nanopore:
                write_output(f"  {Colors.WARNING}{code}{Colors.ENDC}", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All sample codes in samples tab are used in nanopore tab.{Colors.ENDC}", verbose=not silent)
        write_output(f"  {Colors.OKCYAN}Checking run_accession folders and barcode structure...{Colors.ENDC}", verbose=not silent)
        # Structure is minknow_data_dir/runName/sampleName/runAccession — depth 3.
        # Only collect folders at exactly depth 3 to avoid false positives from
        # runName or sampleName dirs being treated as run accessions.
        accession_folder_map = {}
        for run_name in os.listdir(miniknow_data_dir):
            run_name_path = os.path.join(miniknow_data_dir, run_name)
            if not os.path.isdir(run_name_path):
                continue
            for sample_name in os.listdir(run_name_path):
                sample_name_path = os.path.join(run_name_path, sample_name)
                if not os.path.isdir(sample_name_path):
                    continue
                for run_accession in os.listdir(sample_name_path):
                    run_accession_path = os.path.join(sample_name_path, run_accession)
                    if os.path.isdir(run_accession_path):
                        accession_folder_map[run_accession] = run_accession_path
        not_found = []
        no_fastq_pass = []
        no_barcodes = []
        oks = []
        oks_with_extra = []
        barcode_missing = []
        barcode_extra = []
        # Group all expected barcodes by run_accession (one run can span many metadata rows)
        nan_count = 0
        run_accession_barcodes = {}
        for idx, row in df.iloc[1:].iterrows():
            run_accession = str(row[col_map['run_accession']]).strip()
            if not run_accession or run_accession.lower() == 'nan':
                nan_count += 1
                continue
            if run_accession not in run_accession_barcodes:
                run_accession_barcodes[run_accession] = set()
            barcode_val = str(row[barcode_col]).strip()
            if barcode_val and barcode_val.lower() != 'nan':
                barcodes = re.split(r'[;,\s]+', barcode_val)
                run_accession_barcodes[run_accession].update(b for b in barcodes if b)
        if nan_count > 0:
            not_found.append(f"{nan_count} rows with empty run_accession (searched under {miniknow_data_dir})")
        total_runs = len(run_accession_barcodes)
        progress_step = max(1, total_runs // 10)
        for i, (run_accession, expected_barcodes_set) in enumerate(run_accession_barcodes.items()):
            if i % progress_step == 0:
                write_output(f"    {Colors.GREY}Progress: {i+1}/{total_runs}{Colors.ENDC}", verbose=not silent)
            expected_barcodes = sorted(expected_barcodes_set)
            found_folder = accession_folder_map.get(run_accession)
            if not found_folder:
                not_found.append(f"{run_accession}: [NOT FOUND] (searched under {miniknow_data_dir})")
            else:
                fastq_pass_path = os.path.join(found_folder, 'fastq_pass')
                if not os.path.isdir(fastq_pass_path):
                    no_fastq_pass.append(f"{run_accession}: [NO fastq_pass] {fastq_pass_path}")
                else:
                    actual_barcodes = sorted([d for d in os.listdir(fastq_pass_path) if os.path.isdir(os.path.join(fastq_pass_path, d)) and d.lower().startswith('barcode')])
                    if not actual_barcodes:
                        no_barcodes.append(f"{run_accession}: [NO barcodes] {fastq_pass_path}")
                    else:
                        missing = [b for b in expected_barcodes if b not in actual_barcodes]
                        extra = [b for b in actual_barcodes if b not in expected_barcodes]
                        if missing:
                            barcode_missing.append(f"{run_accession}: Missing barcode folders: {', '.join(missing)}")
                        if extra:
                            barcode_extra.append(f"{run_accession}: Unregistered barcode folders ({len(extra)}): {', '.join(extra)}")
                            oks_with_extra.append(f"{run_accession}: [OK, {len(extra)} unregistered] {found_folder} ({len(actual_barcodes)} on disk, {len(expected_barcodes)} in metadata)")
                        else:
                            oks.append(f"{run_accession}: [OK] {found_folder} ({len(actual_barcodes)} barcodes)")
        # Always log verbose output, regardless of silent/verbose mode
        def summarize(lst, label, color=Colors.ENDC, max_items=2):
            if not lst:
                return
            write_output(f"\n{color}{label}:{Colors.ENDC}", verbose=not silent)
            for i, msg in enumerate(lst):
                if max_items is None or i < max_items:
                    write_output(f"  {msg}", verbose=not silent)
                elif i == max_items:
                    write_output(f"  ... and {len(lst) - max_items} more", verbose=not silent)
                    break
        summarize(not_found, "Missing run_accession folders", Colors.FAIL)
        summarize(no_fastq_pass, "Missing fastq_pass folders", Colors.WARNING)
        summarize(no_barcodes, "Missing barcode folders", Colors.WARNING)
        summarize(barcode_missing, "Barcodes listed in metadata but missing in fastq_pass", Colors.WARNING)
        summarize(barcode_extra, "Barcode folders present in fastq_pass but NOT registered in metadata", Colors.WARNING, max_items=None)

        # Reverse check: scan disk for run accession folders not present in metadata.
        # The forward check (above) only catches runs that ARE in metadata but missing on disk.
        # Without this, a run folder present on disk but absent from metadata is silently ignored.
        write_output(f"\n  {Colors.OKCYAN}Checking for run folders on disk NOT registered in metadata...{Colors.ENDC}", verbose=not silent)
        runs_on_disk = set(accession_folder_map.keys())
        runs_in_metadata = set(run_accession_barcodes.keys())
        unregistered_runs = sorted(runs_on_disk - runs_in_metadata)
        if unregistered_runs:
            errors.append(f"Run folders on disk NOT found in metadata: {unregistered_runs}")
            write_output(f"\n{Colors.FAIL}Run folders present on disk but NOT registered in metadata:{Colors.ENDC}", verbose=not silent)
            for run in unregistered_runs:
                folder = accession_folder_map[run]
                write_output(f"  {Colors.FAIL}{run}{Colors.ENDC}  ({folder})", verbose=not silent)
        else:
            write_output(f"  {Colors.OKGREEN}All run folders on disk are registered in metadata.{Colors.ENDC}", verbose=not silent)
        if oks_with_extra:
            write_output(f"\n{Colors.WARNING}OK folders (with unregistered barcodes - check metadata):{Colors.ENDC}", verbose=not silent)
            for msg in oks_with_extra:
                write_output(f"  {msg}", verbose=not silent)
        if oks:
            write_output(f"\n{Colors.OKGREEN}OK folders (all barcodes registered):{Colors.ENDC}", verbose=not silent)
            for msg in oks:
                if len(msg) > 120:
                    parts = msg.split(": [OK] ")
                    if len(parts) == 2:
                        write_output(f"  {parts[0]}: [OK]\n    {parts[1]}", verbose=not silent)
                    else:
                        write_output(f"  {msg[:120]}\n    {msg[120:]}", verbose=not silent)
                else:
                    write_output(f"  {msg}", verbose=not silent)
        write_output(f"  {Colors.OKCYAN}Nanopore metadata folder structure check complete.{Colors.ENDC}", verbose=not silent)
    except Exception as e:
        errors.append(f"Exception while checking nanopore metadata: {e}")
        write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} Exception while checking nanopore metadata: {e}", verbose=not silent)
    return errors

def check_biomeme_metadata_structure(env, silent=False):
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}BIOMEME METADATA STRUCTURE CHECK{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=not silent)
    files_dict = find_biomeme_files(env, verbose=not silent)
    if not files_dict:
        biomeme_data_path = env.get('biomeme_data_path') or env.get('DEFAULT_BIOMEME_DATA_PATH')
        biomeme_input_path = os.path.join(biomeme_data_path, "biomeme_input_data") if biomeme_data_path else "[unknown]"
        write_output(f"  {Colors.FAIL}[NOT FOUND]{Colors.ENDC} No biomeme files found in {biomeme_input_path}", verbose=not silent)
        return None
    # --- Original sample code integrity logic follows ---
    metadata_path = env.get('metadata_file') or env.get('DEFAULT_METADATA_FILE')
    if not metadata_path:
        write_output(f"  {Colors.WARNING}[SKIP]{Colors.ENDC} Missing metadata_file config.", verbose=not silent)
        return files_dict
    metadata_path = os.path.expandvars(os.path.expanduser(metadata_path))
    if not os.path.isfile(metadata_path):
        write_output(f"  {Colors.FAIL}[NOT FOUND]{Colors.ENDC} Metadata file: {metadata_path}", verbose=not silent)
        return files_dict
    try:
        xls = pd.ExcelFile(metadata_path)
        write_output(f"  {Colors.OKCYAN}Sheet names in metadata file: {xls.sheet_names}{Colors.ENDC}", verbose=not silent)
        biomeme_sheet = None
        for sheet in xls.sheet_names:
            if 'biomeme' in sheet.lower():
                biomeme_sheet = sheet
                break
        if not biomeme_sheet:
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'biomeme' sheet found in metadata file.", verbose=not silent)
            return files_dict
        write_output(f"  {Colors.OKCYAN}Loading biomeme tab with header=1...{Colors.ENDC}", verbose=not silent)
        try:
            df = pd.read_excel(xls, sheet_name=biomeme_sheet, header=1)
        except Exception as e:
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} Could not read biomeme tab: {e}", verbose=not silent)
            return files_dict
        sample_code_col = None
        for col in df.columns:
            if 'sample_code' == col.lower():
                sample_code_col = col
                break
        if not sample_code_col:
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'sample_code' column found in biomeme sheet.", verbose=not silent)
            return files_dict
        samples_sheet = None
        for sheet in xls.sheet_names:
            if 'samples' == sheet.lower():
                samples_sheet = sheet
                break
        if not samples_sheet:
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'samples' sheet found in metadata file.", verbose=not silent)
            return files_dict
        write_output(f"  {Colors.OKCYAN}Loading samples tab...{Colors.ENDC}", verbose=not silent)
        df_samples = pd.read_excel(xls, sheet_name=samples_sheet, header=1)
        samples_code_col = None
        for col in df_samples.columns:
            if 'filled out automatically' in col.lower():
                samples_code_col = col
                break
        if not samples_code_col:
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No sample_code column found in samples sheet.", verbose=not silent)
            return files_dict
        write_output(f"  {Colors.OKCYAN}Comparing sample codes...{Colors.ENDC}", verbose=not silent)
        biomeme_sample_codes = set()
        biomeme_code_rows = {}
        for idx, row in df.iloc[1:].iterrows():
            code = str(row[sample_code_col]).strip() if sample_code_col else ''
            if code and code.lower() != 'nan':
                biomeme_sample_codes.add(code)
                biomeme_code_rows[code] = idx + 2
        samples_sample_codes = set(str(val).strip() for i, val in enumerate(df_samples[samples_code_col]) if i != 1 and str(val).strip() and str(val).strip().lower() != 'nan')
        missing_in_samples = sorted([code for code in biomeme_sample_codes if code not in samples_sample_codes])
        unused_in_biomeme = sorted([code for code in samples_sample_codes if code not in biomeme_sample_codes])
        if missing_in_samples:
            write_output(f"\n{Colors.FAIL}Sample codes in biomeme tab NOT found in samples tab:{Colors.ENDC}", verbose=not silent)
            for code in missing_in_samples:
                rownum = biomeme_code_rows.get(code, '?')
                write_output(f"  {Colors.FAIL}{code}{Colors.ENDC} (row {rownum})", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All sample codes in biomeme tab are valid (found in samples tab).{Colors.ENDC}", verbose=not silent)
        if unused_in_biomeme:
            write_output(f"\n{Colors.WARNING}Sample codes in samples tab NOT used in biomeme tab (low severity):{Colors.ENDC}", verbose=not silent)
            for code in unused_in_biomeme:
                write_output(f"  {Colors.WARNING}{code}{Colors.ENDC}", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All sample codes in samples tab are used in biomeme tab.{Colors.ENDC}", verbose=not silent)
        write_output(f"  {Colors.OKCYAN}Biomeme sample_code integrity check complete.{Colors.ENDC}", verbose=not silent)
    except Exception as e:
        write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} Exception while checking biomeme metadata: {e}", verbose=not silent)
    return files_dict

def check_biomeme_run_names(env, files_dict, silent=False):
    errors = []
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}BIOMEME RUN NAME INTEGRITY CHECK{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=not silent)
    write_output(f"  {Colors.OKCYAN}Found biomeme files grouped by country_code and sampling_date:{Colors.ENDC}", verbose=not silent)
    for country_code, date_dict in files_dict.items():
        write_output(f"    {Colors.BOLD}{country_code}{Colors.ENDC}", verbose=not silent)
        for sampling_date, files in date_dict.items():
            write_output(f"      {Colors.OKBLUE}{sampling_date}{Colors.ENDC}", verbose=not silent)
            for f in files:
                write_output(f"        {Colors.GREY}{f}{Colors.ENDC}", verbose=not silent)
    metadata_path = env.get('metadata_file') or env.get('DEFAULT_METADATA_FILE')
    if not metadata_path:
        errors.append("metadata_file not set.")
        write_output(f"  {Colors.FAIL}[MISSING]{Colors.ENDC} metadata_file not set.", verbose=not silent)
        return errors
    metadata_path = os.path.expandvars(os.path.expanduser(metadata_path))
    if not os.path.isfile(metadata_path):
        errors.append(f"Metadata file not found: {metadata_path}")
        write_output(f"  {Colors.FAIL}[NOT FOUND]{Colors.ENDC} Metadata file: {metadata_path}", verbose=not silent)
        return errors
    try:
        xls = pd.ExcelFile(metadata_path)
        biomeme_sheet = None
        for sheet in xls.sheet_names:
            if 'biomeme' in sheet.lower():
                biomeme_sheet = sheet
                break
        if not biomeme_sheet:
            errors.append("No 'biomeme' sheet found in metadata file.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'biomeme' sheet found in metadata file.", verbose=not silent)
            return errors
        df_biomeme = pd.read_excel(xls, sheet_name=biomeme_sheet, header=1)
        run_name_col = None
        for col in df_biomeme.columns:
            if 'biomeme_run_name' == col.lower():
                run_name_col = col
                break
        if not run_name_col:
            errors.append("No 'biomeme_run_name' column found in biomeme sheet.")
            write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} No 'biomeme_run_name' column found in biomeme sheet.", verbose=not silent)
            return errors
        # Skip row 3 (index 2) and any cell with known info/comment text when collecting run names
        info_texts = [
            "content of cell a1 in biomeme result files",
            "content of cell a1 in biomeme result file",
            "info cell",
            "comment cell"
        ]
        metadata_run_names = set(
            str(val).strip() for i, val in enumerate(df_biomeme[run_name_col])
            if i != 2 and str(val).strip() and str(val).strip().lower() != 'nan' and str(val).strip().lower() not in info_texts
        )
        file_run_names = {}
        for country_code, date_dict in files_dict.items():
            for sampling_date, files in date_dict.items():
                for filename in files:
                    biomeme_data_path = env.get('biomeme_data_path') or env.get('DEFAULT_BIOMEME_DATA_PATH')
                    if not biomeme_data_path:
                        errors.append("biomeme_data_path not set.")
                        write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} biomeme_data_path not set.", verbose=not silent)
                        continue
                    file_path = os.path.join(biomeme_data_path, "biomeme_input_data", country_code, sampling_date, filename)
                    try:
                        df_file = pd.read_excel(file_path, header=None)
                        run_name = str(df_file.iloc[0, 1]).strip() if df_file.shape[1] > 1 else ''
                        if run_name and run_name.lower() != 'nan':
                            file_run_names[file_path] = run_name
                    except Exception as e:
                        errors.append(f"Could not read biomeme file: {file_path} Error: {e}")
                        write_output(f"  {Colors.WARNING}[WARN]{Colors.ENDC} Could not read biomeme file: {file_path}\n    Error: {e}", verbose=not silent)
        missing_in_metadata = [f for f, rn in file_run_names.items() if rn not in metadata_run_names]
        unused_in_files = [rn for rn in metadata_run_names if rn not in file_run_names.values()]
        if missing_in_metadata:
            errors.append(f"Run names in biomeme files NOT found in metadata biomeme_run_name column: {[file_run_names[f] for f in missing_in_metadata]}")
            write_output(f"\n{Colors.FAIL}Run names in biomeme files NOT found in metadata biomeme_run_name column:{Colors.ENDC}", verbose=not silent)
            for f in missing_in_metadata:
                write_output(f"  {Colors.FAIL}{file_run_names[f]}{Colors.ENDC} (file: {f})", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All biomeme file run names are valid (found in metadata biomeme_run_name column).{Colors.ENDC}", verbose=not silent)
        if unused_in_files:
            errors.append(f"Run names in metadata biomeme_run_name column NOT used in any biomeme file: {unused_in_files}")
            write_output(f"\n{Colors.WARNING}Run names in metadata biomeme_run_name column NOT used in any biomeme file (low severity):{Colors.ENDC}", verbose=not silent)
            for rn in unused_in_files:
                write_output(f"  {Colors.WARNING}{rn}{Colors.ENDC}", verbose=not silent)
        else:
            write_output(f"\n{Colors.OKGREEN}All biomeme_run_name values in metadata are used in biomeme files.{Colors.ENDC}", verbose=not silent)
        write_output(f"  {Colors.OKCYAN}Biomeme run name integrity check complete.{Colors.ENDC}", verbose=not silent)
    except Exception as e:
        errors.append(f"Exception while checking biomeme run names: {e}")
        write_output(f"  {Colors.FAIL}[ERROR]{Colors.ENDC} Exception while checking biomeme run names: {e}", verbose=not silent)
    return errors

def check_biomeme_sample_ids(env, biomeme_file_path, metadata_path, silent=False):
    errors = []
    """
    For a given biomeme xlsx file, check that all sample IDs from Biomeme_sample_ID in metadata
    (for the matching biomeme_run_name) exist in the biomeme file's sample ID row (row 10, columns B+).
    Report any missing sample IDs.
    """
    import pandas as pd
    import os
    try:
        # Read biomeme xlsx file
        df_biomeme = pd.read_excel(biomeme_file_path, header=None)
        # Extract biomeme_run_name from cell B1
        biomeme_run_name = str(df_biomeme.iloc[0, 1]).strip() if df_biomeme.shape[1] > 1 else None
        if not biomeme_run_name:
            write_output(f"{Colors.FAIL}[ERROR]{Colors.ENDC} Could not extract biomeme_run_name from {biomeme_file_path}", verbose=not silent)
            return errors
        # Extract sample IDs from row 10 (index 9), columns B+ (index 1+)
        sample_id_row = df_biomeme.iloc[9, 1:]
        sample_ids_in_file = set(str(x).strip() for x in sample_id_row if str(x).strip() and str(x).strip().lower() != 'nan')
        # Read metadata biomeme tab
        xls = pd.ExcelFile(metadata_path)
        biomeme_sheet = None
        for sheet in xls.sheet_names:
            if 'biomeme' in sheet.lower():
                biomeme_sheet = sheet
                break
        if not biomeme_sheet:
            write_output(f"{Colors.FAIL}[ERROR]{Colors.ENDC} No 'biomeme' sheet found in metadata file.", verbose=not silent)
            return errors
        df_meta = pd.read_excel(xls, sheet_name=biomeme_sheet, header=1)
        # Find biomeme_run_name and Biomeme_sample_ID columns
        run_name_col = None
        sample_id_col = None
        for col in df_meta.columns:
            if 'biomeme_run_name' == col.lower():
                run_name_col = col
            if 'biomeme_sample_id' == col.lower():
                sample_id_col = col
        if not run_name_col or not sample_id_col:
            write_output(f"{Colors.FAIL}[ERROR]{Colors.ENDC} Missing biomeme_run_name or biomeme_sample_id column in metadata.", verbose=not silent)
            return errors
        # Find the row in metadata matching biomeme_run_name
        meta_row = df_meta[df_meta[run_name_col].astype(str).str.strip() == biomeme_run_name]
        if meta_row.empty:
            write_output(f"{Colors.FAIL}[ERROR]{Colors.ENDC} biomeme_run_name '{biomeme_run_name}' not found in metadata.", verbose=not silent)
            return errors
        # Get comma-separated sample IDs from Biomeme_sample_ID
        meta_sample_ids = set()
        for val in meta_row[sample_id_col]:
            meta_sample_ids.update(str(val).strip().split(','))
        meta_sample_ids = set(x.strip() for x in meta_sample_ids if x.strip())
        # Check for missing sample IDs
        missing_ids = sorted([sid for sid in meta_sample_ids if sid not in sample_ids_in_file])
        if missing_ids:
            errors.append(f"Sample IDs from metadata missing in biomeme file '{os.path.basename(biomeme_file_path)}': {missing_ids}")
            write_output(f"\n{Colors.FAIL}Sample IDs from metadata missing in biomeme file '{os.path.basename(biomeme_file_path)}':{Colors.ENDC}", verbose=not silent)
            for sid in missing_ids:
                write_output(f"  {Colors.FAIL}{sid}{Colors.ENDC}", verbose=not silent)
        else:
            write_output(f"{Colors.OKGREEN}All sample IDs from metadata are present in biomeme file '{os.path.basename(biomeme_file_path)}'.{Colors.ENDC}", verbose=not silent)
    except Exception as e:
        errors.append(f"Exception during biomeme sample ID check: {e}")
        write_output(f"{Colors.FAIL}[ERROR]{Colors.ENDC} Exception during biomeme sample ID check: {e}", verbose=not silent)
    return errors

def check_biomeme_sample_id_integrity(env, files_dict, silent=False):
    errors = []
    write_output(f"\n{Colors.BOLD}{'-'*60}\n{Colors.OKBLUE}BIOMEME SAMPLE ID INTEGRITY CHECK{Colors.ENDC}\n{'-'*60}{Colors.ENDC}", verbose=not silent)
    metadata_path = env.get('metadata_file') or env.get('DEFAULT_METADATA_FILE')
    for country_code, date_dict in files_dict.items():
        for sampling_date, files in date_dict.items():
            for filename in files:
                biomeme_data_path = env.get('biomeme_data_path') or env.get('DEFAULT_BIOMEME_DATA_PATH')
                file_path = os.path.join(biomeme_data_path, "biomeme_input_data", country_code, sampling_date, filename)
                file_errors = check_biomeme_sample_ids(env, file_path, metadata_path, silent=silent)
                errors.extend(file_errors)
    write_output(f"  {Colors.OKCYAN}Biomeme sample ID integrity check complete.{Colors.ENDC}", verbose=not silent)
    return errors

def main():
    parser = argparse.ArgumentParser(description="ODIN pipeline integrity check")
    parser.add_argument('--verbose', action='store_true', help='Show detailed output for all checks')
    args = parser.parse_args()
    verbose = args.verbose
    env = dict(os.environ)
    check_paths(env)
    check_specific_files(env)
    nanopore_errors = check_nanopore_metadata_structure(env, silent=not verbose)
    files_dict = check_biomeme_metadata_structure(env, silent=not verbose)
    biomeme_run_name_errors = []
    biomeme_sample_id_errors = []
    summary_banner = f"\n{Colors.BOLD}{Colors.OKBLUE}{'-'*60}{Colors.ENDC}"
    summary_title = f"{Colors.BOLD}{Colors.OKBLUE}INTEGRITY CHECK SUMMARY{Colors.ENDC}"
    summary_banner_end = f"{Colors.BOLD}{Colors.OKBLUE}{'-'*60}{Colors.ENDC}"
    if not files_dict:
        # Print summary banner and error in red if no biomeme files found
        write_output(summary_banner, verbose=True, force_console=True)
        write_output(summary_title, verbose=True, force_console=True)
        write_output(summary_banner_end, verbose=True, force_console=True)
        write_output(f"{Colors.FAIL}Errors found in integrity checks!{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"  Nanopore errors: {len(nanopore_errors)}", verbose=True, force_console=True)
        write_output(f"  {Colors.FAIL}No biomeme files found.{Colors.ENDC}", verbose=True, force_console=True)
        if not verbose:
            write_output(f"\n{Colors.WARNING}For more details, rerun this script with the --verbose flag.{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"\n{Colors.BOLD}Integrity check complete.{Colors.ENDC}", verbose=True, force_console=True)
        return
    if files_dict:
        biomeme_run_name_errors = check_biomeme_run_names(env, files_dict, silent=not verbose)
        biomeme_sample_id_errors = check_biomeme_sample_id_integrity(env, files_dict, silent=not verbose)
    # Final reporting summary banner
    write_output(summary_banner, verbose=True, force_console=True)
    write_output(summary_title, verbose=True, force_console=True)
    write_output(summary_banner_end, verbose=True, force_console=True)
    if nanopore_errors or biomeme_run_name_errors or biomeme_sample_id_errors:
        write_output(f"{Colors.FAIL}Errors found in integrity checks!{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"  Nanopore errors: {len(nanopore_errors)}", verbose=True, force_console=True)
        if files_dict:
            write_output(f"  Biomeme run name errors: {len(biomeme_run_name_errors)}", verbose=True, force_console=True)
            write_output(f"  Biomeme sample ID errors: {len(biomeme_sample_id_errors)}", verbose=True, force_console=True)
        if not verbose:
            write_output(f"\nTo see detailed error output, re-run this script with the '--verbose' flag.", verbose=True, force_console=True)
    else:
        write_output(f"{Colors.OKGREEN}No errors found in biomeme or nanopore checks.{Colors.ENDC}", verbose=True, force_console=True)
        write_output(f"  Nanopore errors: 0", verbose=True, force_console=True)
        if files_dict:
            write_output(f"  Biomeme run name errors: 0", verbose=True, force_console=True)
            write_output(f"  Biomeme sample ID errors: 0", verbose=True, force_console=True)
    write_output(f"\n{Colors.BOLD}Integrity check complete.{Colors.ENDC}", verbose=True, force_console=True)

if __name__ == "__main__":
    main()
