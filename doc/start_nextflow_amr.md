# start_nextflow_amr.sh

## Overview

This script runs the epi2me-labs/wf-metagenomics pipeline with AMR (Antimicrobial Resistance) detection enabled. It processes Nanopore sequencing data through the wf-metagenomics workflow to identify antimicrobial resistance genes in your samples.

## Usage

```bash
./scripts/start_nextflow_amr.sh [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]
```
### Options

- `-h`, `--help`  
  Display help and exit.


### Arguments

- `minknow_data_dir`: Directory containing MinKNOW output folders
- `output_dir`: Root directory of output data
- `run_accession`: Run accession path (runName/sampleName/run_accession) within minknow_data_dir
- `metadata_file`: Path to the metadata Excel file
- `venv_folder`: Path to Python virtual environment (optional)

If arguments are not provided, the script will prompt for them interactively.

## Default Settings

- **Database Set**: PlusPF-8 (optimized for pathogen identification)
- **AMR Database**: card (Comprehensive Antibiotic Resistance Database)

## Output

The script will create an output directory at:

```
[output_dir]/nanopore_processed/outputs_wf_metagenomics_amr/[run_accession]
```

The output directory contains:
- Taxonomic classification results
- AMR gene identification
- Detailed reports in HTML and other formats
- Log files from the pipeline execution

## Examples

### Basic Usage with Interactive Prompts

```bash
./scripts/start_nextflow_amr.sh
```

### Providing All Arguments

```bash
./scripts/start_nextflow_amr.sh /path/to/minknow/data /path/to/output run_20240315_1523 /path/to/metadata.xlsx /home/user/venv
```

### Using Configuration Values

If you've run other pipeline scripts before, the script will use saved paths from previous runs as defaults.
The paths are stored in your user config at `~/.odin_ml/odin_paths.txt`. You can edit this file to change your defaults. For new installations, the default config is `scripts/odin_paths.txt`.

## Pipeline design and provenance

The choice of `epi2me-labs/wf-metagenomics` for AMR detection was specified by the WP3 bioinformatics team in an internal design note dated 19 August 2025, which also defined the three analysis workflows and their output directory structure. The reference nextflow command from that note was:

```bash
nextflow run epi2me-labs/wf-metagenomics \
  --fastq '/mnt/c/data/<run_path>/fastq_pass/' \
  --database_set 'PlusPF-8' \
  --amr --amr_db card \
  --out_dir '/mnt/c/.../nanopore_processed/outputs_wf_metagenomics_amr/<run_accession>'
```

Key design decisions recorded in that note:
- `epi2me-labs/wf-metagenomics` is used for both AMR and SSU analysis (same pipeline, different database and flags).
- The AMR database is **CARD** (`--amr_db card`); `--database_set PlusPF-8` drives the taxonomic classification component of the same workflow.
- Unlike `start_nextflow.sh` (taxprofiler), neither the AMR nor the SSU script requires a `databases.csv` or an `all_samples_*.csv` samplesheet.
- Output lands in `nanopore_processed/outputs_wf_metagenomics_amr/` (AMR) and `nanopore_processed/outputs_wf_metagenomics_ssu/` (SSU), parallel to the taxprofiler output directory.
