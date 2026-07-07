# Bash Scripts Reference

## Table of Contents

### Pipeline Starters
- [start_biomeme.sh](#start_biomemesh) – Run Biomeme qPCR data processing workflow.
- [start_mpox.sh](#start_mpoxsh) – Run Mpox sequencing and phylogenetic analysis pipeline.
- [start_nextflow.sh](#start_nextflowsh) – Launch nf-core/taxprofiler pipeline for Nanopore data.
- [start_nextflow_amr.sh](#start_nextflow_amrsh) – Run epi2me-labs/wf-metagenomics pipeline with AMR detection enabled.
- [start_nextflow_ssu.sh](#start_nextflow_ssush) – Run epi2me-labs/wf-metagenomics pipeline for SSU rRNA analysis.

### Post-processing
- [extract_reads.sh](#extract_readssh) – Align Kraken2-classified reads to a pathogen reference, extract mapped reads, and write a confidence report.

### Utilities & Helpers
- [start_enlighten.sh](#start_enlightensh) – Set up and start Enlighten visualization container.
- [stop_enlighten.sh](#stop_enlightensh) – Stop the Enlighten visualization container.
- [config_utils.sh](#config_utilssh) – Shared utility functions for scripts.
- [create_kraken_datasets.sh](#create_kraken_datasetssh) – Create datasets from Kraken2 output for Enlighten.
- [create_mpox_samples_csv.py](#create_mpox_samples_csvpy) – Generate sample sheet CSV for Mpox pipeline.
- [create_all_samples_csv.py](#create_all_samples_csvpy) – Generate sample sheet CSV for Taxprofiler pipeline.
- [parse_amr_json.py](#parse_amr_jsonpy) – Parse AMR JSON output and create tabular datasets.
- [concatenate_fastq_by_sample.py](#concatenate_fastq_by_samplepy) – Concatenate FASTQ files across multiple runs.
- [verify_metadata.sh](#verify_metadatash) – Verify Nanopore directory structure using metadata.
- [verify_nanopore_metadata.py](#verify_nanopore_metadatapy) – Python script to verify Nanopore metadata.
- [get_run_metadata.py](#get_run_metadatapy) – Extract metadata for a specific run accession.
- [integrity_check.py](#integrity_checkpy) – Check Python environment and package dependencies.
- [nanopore_metadata.py](#nanopore_metadatapy) – Core module for metadata operations (library).

### Advisory & Troubleshooting
- [Error with mkdir: Stale drvfs State in WSL](#advisory-stale-drvfs-state-in-wsl)

This document describes the main bash scripts in the `pipeline_scripts/scripts` folder, their arguments, and behaviour.

---

## `start_biomeme.sh`

Runs the Biomeme qPCR data processing workflow for eDNA analysis.

### Arguments

```bash
start_biomeme.sh [biomeme_data_path] [metadata_file]
```

- `biomeme_data_path`: **Folder containing Biomeme qPCR results** (Excel files).
- `metadata_file`: Path to metadata file (optional).

Missing arguments are prompted interactively.

### Behaviour

- Loads configuration and utility functions.
- Prompts for required directories and metadata.
- Processes Biomeme qPCR Excel files to extract Cq values and calculate abundance.
- Merges results with metadata and assay parameters.
- Flags data quality and applies NTC thresholds.
- Outputs processed results for downstream analysis.

---

## `start_mpox.sh`

Runs the artic-mpxv-nf Nextflow pipeline for Mpox (Monkeypox virus) sequencing data and downstream phylogenetic analysis with squirrel.

### Arguments

```bash
start_mpox.sh [minknow_data_dir] [output_dir] [run_accession]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path to run accession (runName/sampleName/run_accession) within `minknow_data_dir`.

Missing arguments are prompted interactively.

### Behaviour

- Loads configuration and utility functions.
- Prompts for required directories, metadata, clade, and scheme version.
- Prepares output directories.
- Generates a sample sheet CSV using `create_mpox_samples_csv.py`.
- Runs the artic-mpxv-nf Nextflow pipeline.
- Runs squirrel for phylogenetic analysis on pipeline results.

---

## `start_nextflow.sh`

Launches the nf-core/taxprofiler pipeline for Nanopore sequencing data.

### Arguments

```bash
start_nextflow.sh [OPTIONS] [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [databases_file] [venv_folder]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path (runName/sampleName/run_accession) within `minknow_data_dir`.
- `metadata_file`: Path to the `metadata.xlsx` file.
- `databases_file`: Path to the `databases.csv` file.
- `venv_folder`: Path to Python virtual environment folder (leave empty to use base environment).

If any arguments are omitted, the script will prompt for them interactively. For `run_accession`, a selection menu is shown if not provided.

### Behaviour

- Validates input directories and files.
- Extracts runName, sampleName, and run_accession from the provided path.
- Calls `verify_nanopore_metadata.py` to validate that the metadata matches the directory structure.
- Builds output directory structure based on metadata.
- Concatenates fastq.gz files for each barcode.
- Generates a sample CSV for Nextflow using the `create_all_samples_csv.py` script.
- Runs the nf-core/taxprofiler pipeline.
- Cleans up temporary files after completion.
- Calls `create_kraken_datasets.py` to generate visualization datasets from the pipeline results.
- Saves user inputs to a config file for future runs.

---

## `start_nextflow_amr.sh`

Runs the epi2me-labs/wf-metagenomics Nextflow pipeline with AMR (Antimicrobial Resistance) detection enabled for Nanopore sequencing data.

### Arguments

```bash
start_nextflow_amr.sh [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path (runName/sampleName/run_accession) within `minknow_data_dir`.
- `metadata_file`: Path to the metadata Excel file.
- `venv_folder`: Path to Python virtual environment (optional).

Missing arguments are prompted interactively.

### Default Settings

- **Database Set**: PlusPF-8 (optimized for pathogen identification)
- **AMR Database**: CARD (Comprehensive Antibiotic Resistance Database)

### Behaviour

- Validates input directories and files.
- Prompts for required arguments.
- Verifies metadata with `verify_nanopore_metadata.py`.
- Concatenates FASTQ files by barcode using `concatenate_fastq_by_sample.py`.
- Runs epi2me-labs/wf-metagenomics with `--amr --amr_db card` flags.
- Outputs results to `nanopore_processed/outputs_wf_metagenomics_amr/`.

---

## `start_nextflow_ssu.sh`

Runs the epi2me-labs/wf-metagenomics Nextflow pipeline focused on SSU (Small Subunit) ribosomal RNA analysis using the SILVA database for taxonomic classification.

### Arguments

```bash
start_nextflow_ssu.sh [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path (runName/sampleName/run_accession) within `minknow_data_dir`.
- `metadata_file`: Path to the metadata Excel file.
- `venv_folder`: Path to Python virtual environment (optional).

Missing arguments are prompted interactively.

### Default Settings

- **Database Set**: SILVA_138_1 (16S/18S rRNA taxonomic classification)

### Behaviour

- Validates input directories and files.
- Prompts for required arguments.
- Verifies metadata with `verify_nanopore_metadata.py`.
- Concatenates FASTQ files by barcode using `concatenate_fastq_by_sample.py`.
- Runs epi2me-labs/wf-metagenomics with SILVA database.
- Outputs results to `nanopore_processed/outputs_wf_metagenomics_ssu/`.

---

## `start_enlighten.sh`

Sets up and starts (or restarts) the Enlighten visualization containers using Docker Compose.

### Arguments

```bash
start_enlighten.sh [enlighten_data_path]
```

- `enlighten_data_path`: Absolute path to the Enlighten data directory (defaults to `enlighten/data` if not provided).

### Behaviour

- Resolves the Enlighten data path (from argument, config, or default).
- Exports `HOST_DATA_PATH` and `HOST_PUBLIC_FILES_PATH` environment variables for Docker Compose.
- Verifies the data and public files directories exist (creates the public files directory if needed).
- Runs `docker compose down` followed by `docker compose up -d` in the `enlighten/` directory.
- Makes the Enlighten visualization available at http://localhost (port 80 → client, port 8081 → API).

---

## `stop_enlighten.sh`

Stops the Enlighten visualization container.

### Arguments

```bash
stop_enlighten.sh
```

No arguments are required.

### Behaviour

- Runs `docker compose down` in the `enlighten/` directory.
- Finds and removes any leftover containers by project label.
- Uses `set -euo pipefail` for strict error handling.

---

## `config_utils.sh`

A utility script containing shared functions used by other scripts.

### Key Functions

- `resolve_path`: Converts Windows paths to WSL paths, handles relative and absolute paths.
- `is_valid_venv` / `setup_venv`: Validates and sets up Python virtual environment.
- `activate_venv`: Activates venv and exports `PYTHON_CMD` variable.
- `get_path`: Prompts for file/directory paths with validation (directory, file, or none).
- `set_config_value`: Updates configuration file with key-value pairs without removing others.
- `select_run_accession` / `get_run_accession`: Interactive menu to pick runs from MinKNOW structure.
- `build_nextflow_outdir`: Builds the output directory path for Nextflow results.
- `run_python_script`: Executes Python commands with red error highlighting.
- `verify_run_structure`: Checks for fastq_pass and barcode directories.

This script is not meant to be executed directly but is sourced by other scripts.

### Config File Priority

1. User override: `~/.odin_ml/odin_paths.txt` (highest priority)
2. Default: `scripts/odin_paths.txt` (checked into repo)
3. Old location: `scripts/nanopore_paths.txt` (fallback)

---

## `create_kraken_datasets.sh`

Creates datasets from Kraken2 output files for visualization in Enlighten.

### Arguments

```bash
create_kraken_datasets.sh [kraken2_path] [metadata_file] [pathogens_file] [feather_output_path] [xlsx_output_path] [venv_folder]
```

- `kraken2_path`: Path to Kraken2 output files.
- `metadata_file`: Path to the metadata Excel file.
- `pathogens_file`: Path to the pathogens database file.
- `feather_output_path`: Directory for Feather format output files (for Enlighten).
- `xlsx_output_path`: Directory for Excel format output files.
- `venv_folder`: Path to Python virtual environment (optional).

Missing arguments are prompted for interactively.

### Behaviour

- Processes Kraken2 output and combines with metadata and pathogen info.
- Splits datasets by specified metadata fields (default: country).
- Generates Feather format files for Enlighten visualization in the specified directory.
- Generates Excel format files in the specified directory.
- Saves configuration for future runs.

---

## `create_mpox_samples_csv.py`

Python script to generate a sample sheet CSV for the artic-mpxv-nf pipeline.

### Arguments

- Input: run accession, fastq directory, output CSV path, metadata file.

### Behaviour

- Reads metadata and fastq files.
- Produces a CSV file listing samples and relevant information for the pipeline.

---

## `verify_metadata.sh`

Verifies the expected directory structure and files for Nanopore sequencing data using metadata.

### Arguments

```bash
verify_metadata.sh [OPTIONS] [minknow_data_dir] [metadata_file] [venv_folder] [run_accession]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `metadata_file`: Path to the metadata Excel file.
- `venv_folder`: Path to Python virtual environment (optional).
- `run_accession`: Specific run accession to verify (optional).

If arguments are omitted, the script prompts for them. If `run_accession` is provided, only that run is verified; otherwise, all runs in the metadata file are checked.

### Behaviour

- Prompts for missing arguments with defaults from previous runs.
- Activates the specified Python environment if provided.
- Calls a Python script to verify the existence of required directories and files.
- Saves configuration for future runs.

---

## `create_all_samples_csv.py`

Python script to generate a sample sheet CSV for the nf-core/taxprofiler pipeline.

### Arguments

```bash
create_all_samples_csv.py --metadata_file <path> --input_seqs_directory <path> --output_csv_file <path> (--run_accession <id> | --sample_id <id>)
```

- `--metadata_file`: Path to the metadata Excel file (required).
- `--input_seqs_directory`: Directory containing concatenated `*.fastq.gz` files (required).
- `--output_csv_file`: Output CSV file path (required).
- `--run_accession`: Process specific run accession (mutually exclusive with `--sample_id`).
- `--sample_id`: Process all runs for specific sample ID (mutually exclusive with `--run_accession`).

### Behaviour

- Reads nanopore metadata from Excel file.
- Extracts barcodes for the given identifier from metadata.
- Recursively searches `input_seqs_directory` for `*.fastq.gz` files.
- Generates a CSV file with columns: `sample`, `run_accession`, `instrument_platform`, `fastq_1`.
- Only includes barcodes that are present in the metadata.
- Outputs sample sheet compatible with nf-core/taxprofiler.

---

## `parse_amr_json.py`

Python script to parse Antimicrobial Resistance (AMR) JSON files from Nextflow wf-metagenomics output and convert to tabular format.

### Arguments

```bash
parse_amr_json.py --data_path <path> --metadata_excel <path> -o <output_dir> [--show-summary]
```

- `--data_path`: Root data path containing nanopore_processed directory with AMR output files (required).
- `--metadata_excel`: Path to metadata Excel file defining which samples to process (required).
- `-o, --output`: Output directory for resulting files (required).
- `--show-summary`: Display summary statistics about parsed data (optional).

### Behaviour

- Reads AMR JSON files for samples defined in metadata Excel.
- Finds connected run accessions based on sample_id, sampling_date, and barcode.
- Prioritizes merged data directories when available.
- Flattens nested JSON structure into tabular format.
- Enriches data with metadata and geographic information.
- Outputs three file formats: CSV, Feather (for incremental updates), and Excel.
- Generates summary statistics by resistance type.
- Supports incremental updates by merging with existing data.

**See also:** [README_AMR_PARSER.md](README_AMR_PARSER.md) for detailed documentation.

---

## `concatenate_fastq_by_sample.py`

Python script to concatenate FASTQ files from multiple sequencing runs that belong to the same sample.

### Arguments

```bash
concatenate_fastq_by_sample.py --minknow_data_dir <path> --output_dir <path> --metadata_file <path> --tmp_dir <path> (--run_accession <id> | --sample_id <id>)
```

- `--minknow_data_dir`: Root directory containing MinKNOW output folders (required).
- `--output_dir`: Root output directory (required, kept for compatibility).
- `--metadata_file`: Path to metadata Excel file (required).
- `--tmp_dir`: Temporary directory for concatenated files (required).
- `--run_accession`: Process specific run accession (mutually exclusive with --sample_id).
- `--sample_id`: Process all runs for specific sample ID (mutually exclusive with --run_accession).

### Behaviour

- Identifies connected runs by matching sample_id, sampling_date, and barcode.
- For `--run_accession`: Displays interactive prompt to choose between all connected runs or single run.
- For `--sample_id`: Automatically processes all matching runs.
- Recursively searches MinKNOW directory structure for fastq_pass directories.
- Validates metadata consistency across runs.
- Concatenates FASTQ files by barcode using efficient 8 MB chunk processing.
- Preserves gzip compression without decompression/recompression.
- Outputs concatenated files with appropriate naming (sampleName or merged_runID).
- Creates identifier file for bash script integration.

**See also:** [README_CONCATENATE_FASTQ.md](README_CONCATENATE_FASTQ.md) for detailed documentation.

---

## `verify_nanopore_metadata.py`

Python script to verify that Nanopore sequencing directory structure matches metadata expectations.

### Arguments

```bash
verify_nanopore_metadata.py --minknow_data_dir <path> --metadata_file <path> [--run_accession <id>]
```

- `--minknow_data_dir`: Directory containing MinKNOW output folders (required).
- `--metadata_file`: Path to metadata Excel file (required).
- `--run_accession`: Specific run accession to verify (optional, verifies all if omitted).

### Behaviour

- Reads nanopore metadata from Excel file.
- Filters to specific run_accession if provided, otherwise checks all runs.
- Searches for run_accession directories within MinKNOW data structure.
- Verifies existence of fastq_pass directories.
- Validates presence of expected barcode directories.
- Checks for FASTQ files within each barcode directory.
- Reports missing directories, barcodes, or files.
- Exits with error if validation fails.
- Provides detailed error messages for troubleshooting.

---

## `get_run_metadata.py`

Python script to extract and display metadata for a specific run accession.

### Arguments

```bash
get_run_metadata.py <metadata_file> <run_accession> [<run_path>]
```

- `metadata_file`: Path to metadata Excel file (required).
- `run_accession`: Run accession ID to query (required).
- `run_path`: Optional path in format runName/sampleName/run_accession (defaults to run_accession).

### Behaviour

- Reads nanopore metadata from Excel file.
- Extracts runName and sampleName from the provided path.
- Queries metadata for the specified run_accession.
- Extracts sampling_site_id from sample_id using regex pattern.
- Outputs key-value pairs for shell script consumption:
  - `sampling_site_id=<value>`
  - `sampling_date=<value>`
- Exits with status 0 on success, 1 on error.
- Used by bash scripts to retrieve metadata dynamically.

---

## `integrity_check.py`

Python script to verify that the Python environment has all required dependencies installed.

### Arguments

```bash
integrity_check.py [--verbose]
```

- `--verbose`: Display detailed output (optional).

### Behaviour

- Reads `requirements.txt` to determine required packages.
- Attempts to import each required package.
- Maps PyPI package names to Python import names when they differ.
- Reports missing packages with installation instructions.
- Validates that key dependencies (pandas, openpyxl, etc.) are available.
- Uses color-coded output for easy identification of issues.
- Logs all checks to `integrity_check.log` file.
- Exits with status 0 if all dependencies are satisfied, 1 otherwise.
- Useful for troubleshooting environment setup issues.

---

## `nanopore_metadata.py`

Core Python module providing metadata operations used by other scripts. This is a library module, not meant to be executed directly.

### Key Functions

- `read_nanopore_metadata()`: Read and parse metadata from Excel file.
- `load_sites_df()`: Load geographic site information.
- `get_run_metadata()`: Retrieve metadata for specific run accession.
- `get_connected_run_accessions()`: Find runs with matching sample_id, sampling_date, and barcode.
- `extract_site_and_type_from_sample_id()`: Parse sample IDs to extract site and type.
- `extract_run_components()`: Parse run paths to extract runName, sampleName, run_accession.
- `ensure_columns()`: Validate DataFrame has required columns.
- `set_column_dtypes()`: Convert DataFrame column data types.
- `merge_with_existing_file()`: Merge new data with existing Feather files for incremental updates.
- `warn_list()`: Display warnings for missing items.

### Usage

This module is imported and used by other Python scripts in the pipeline:
- `parse_amr_json.py`
- `concatenate_fastq_by_sample.py`
- `create_kraken_datasets.py`
- `create_all_samples_csv.py`
- `create_mpox_samples_csv.py`
- `verify_nanopore_metadata.py`
- `get_run_metadata.py`

---

## Advisory: Stale drvfs State in WSL

> **Note:**
>
> Occasionally, scripts may fail with an error from `mkdir -p` such as:
>
> ```
> mkdir: cannot create directory '...': File exists
> ```
>
> This is often caused by a **stale drvfs state** in Windows Subsystem for Linux (WSL), where the filesystem view becomes out of sync with Windows.
>
> **Solution:**
>
> To resolve this, reset WSL by running:
>
> ```bash
> wsl --shutdown
> ```
>
> Then restart your WSL session and rerun the script. This will refresh the filesystem state and prevent such errors.
