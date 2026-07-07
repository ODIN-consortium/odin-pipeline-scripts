# start_nextflow.sh

## Overview
This script launches the nf-core/taxprofiler pipeline to process Nanopore sequencing data. The script will verify input directories and files before running.

## Before you start (first-time setup)

You will be prompted for four paths the first time you run the script. After the first run, your choices are saved to `~/.odin_ml/odin_paths.txt` and used as defaults on subsequent runs. You can also edit that file directly.

### MinKNOW data directory

The root folder where MinKNOW writes its sequencing output. Inside it you will find subfolders named after your run experiment, sample, and run accession:

```
/mnt/e/ODIN/MOBILE_LAB_NANOPORE/
  ExperimentName/
    SampleName/
      20250912_1649_MC-113870_AYL009_4265a8e3/   ← run accession
        fastq_pass/
          barcode01/
          barcode02/
```

The script scans this directory to present a numbered menu of available run accessions.

### Output directory

Where processed results are written. A folder `nanopore_processed/` is created here automatically. Choose a location with enough free disk space (several GB per run). Example: `/mnt/e/ODIN/data`

### Databases file (`databases.csv`)

A CSV file that lists the Kraken2 (or other taxonomic) databases to use. It must have the columns:

```
tool,db_name,db_params,db_path
kraken2,combined_pathogens,--quick,/home/odin-ml/store_dir/combined_pathogens
```

- `tool` — must be `kraken2`
- `db_name` — a short label used in output filenames
- `db_params` — extra Kraken2 flags (use `--quick` for faster but approximate results, or leave blank)
- `db_path` — absolute path to the Kraken2 database directory (inside WSL/Linux, e.g. `/mnt/e/ODIN/databases/combined_pathogens`)

A template is included at `input_sheets/databases.csv`. Copy and edit it to match your database locations.

### Metadata file

The ODIN metadata Excel workbook (`.xlsx`) that registers your samples and run accessions. The script verifies that the selected run accession is present in this file before proceeding.

## Usage

```bash
start_nextflow.sh [OPTIONS] [minknow_data_dir] [output_dir] [run_accession] [metadata_file]  [databases_file] [venv_folder]
```

### Options

- `-h`, `--help`  
  Display help and exit.

- `--profile NAME`  
  Nextflow profile to use. Default: `odin` (4 CPU / 16 GB). Use `odin_big` for large samples (16 CPU / 31 GB).

- `--save-reads`  
  Save Kraken2 classified and unclassified reads (`--kraken2_save_reads --kraken2_save_readclassifications`). Required if you want to run `extract_reads.sh` afterwards.

- `--mpox-clade CLADE`  
  After the pipeline completes, automatically extract reads and run alignment for the given clade using `extract_reads.sh`. Implies `--save-reads`. Valid values: `cladeia`, `cladeib`, `cladeii`, `cladeiia`, `cladeiib`. For non-Mpox pathogens, use `--save-reads` and run `extract_reads.sh` manually.

- `--auto-merge`  
  Automatically merge all related run accessions without prompting.

- `--force`  
  Overwrite existing output directory.

- `--skip-existing`  
  Skip runs that already have output.

### Arguments

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path (runName/sampleName/run_accession) within `minknow_data_dir`.
- `metadata_file`: Path to the `metadata.xlsx` file.
- `databases_file`: Path to the `databases.csv` file.
- `venv_folder`:Path to Python virtual environment folder (leave empty to use base environment).

If any arguments are omitted, the script will prompt you to enter the missing parameters interactively.

## Output
The script will create an output directory at:
```
[output_dir]/nanopore_processed/outputs_taxprofiler/[run_accession]
```

After the Nextflow pipeline completes, the script also calls `create_kraken_datasets.py` to generate Feather and Excel datasets for Enlighten visualization.

### Key Steps

1. Verifies metadata matches directory structure using `verify_nanopore_metadata.py`.
2. Concatenates FASTQ files per barcode using `concatenate_fastq_by_sample.py`.
3. Generates a sample CSV using `create_all_samples_csv.py`.
4. Runs `nextflow run nf-core/taxprofiler` with `--run_kraken2 --run_krona` (plus `--kraken2_save_reads --kraken2_save_readclassifications` if `--save-reads` or `--mpox-clade` is set).
5. Cleans up temporary concatenated files.
6. Creates Kraken2 datasets (Feather/CSV/Excel) for Enlighten.
7. If `--mpox-clade` is set: loops over all `kraken2/*/` database folders and calls `extract_reads.sh` for each.

## Examples
### Save reads and auto-extract Mpox reads
```bash
start_nextflow.sh --mpox-clade cladeii
```

### Save reads only (for manual extraction later)
```bash
start_nextflow.sh --save-reads
```

### Use odin_big profile for a large run
```bash
start_nextflow.sh --profile odin_big --mpox-clade cladeii
```

### Basic Usage with Interactive Prompts

```bash
start_nextflow.sh
```

### Providing All Arguments
```bash
start_nextflow.sh /mnt/data/minknow /mnt/data/output run1/sampleA/20240101 metadata.xlsx databases.csv /home/user/venv
```

### Using Configuration Values

After the first run your paths are saved to `~/.odin_ml/odin_paths.txt` and used as defaults on the next run. You can edit this file directly to change any default:

```bash
nano ~/.odin_ml/odin_paths.txt
```

For a fresh installation before any run, the fallback defaults are in `scripts/odin_paths.txt`.
