# start_nextflow_ssu.sh

## Overview

This script runs the epi2me-labs/wf-metagenomics pipeline focused on SSU (Small Subunit) ribosomal RNA analysis. It processes Nanopore sequencing data through the wf-metagenomics workflow using the SILVA database for taxonomic classification based on 16S/18S rRNA gene sequences.

## Usage

```bash
./scripts/start_nextflow_ssu.sh [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]
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

- **Database Set**: SILVA_138_1 (optimized for 16S/18S rRNA taxonomic classification)

## Output

The script will create an output directory at:

```
[output_dir]/nanopore_processed/outputs_wf_metagenomics_ssu/[run_accession]
```

The output directory contains:
- Taxonomic classification results based on SSU rRNA
- Read mapping statistics
- Detailed reports in HTML and other formats
- Log files from the pipeline execution

## Examples

### Basic Usage with Interactive Prompts

```bash
./scripts/start_nextflow_ssu.sh
```

### Providing All Arguments

```bash
./scripts/start_nextflow_ssu.sh /path/to/minknow/data /path/to/output run_20240315_1523 /path/to/metadata.xlsx /home/user/venv
```

### Using Configuration Values

If you've run other pipeline scripts before, the script will use saved paths from previous runs as defaults.
The paths are stored in your user config at `~/.odin_ml/odin_paths.txt`. You can edit this file to change your defaults. For new installations, the default config is `scripts/odin_paths.txt`.

## Pipeline design and provenance

The choice of `epi2me-labs/wf-metagenomics` for SSU rRNA analysis was specified by the WP3 bioinformatics team in an internal design note dated 19 August 2025, alongside the AMR and taxprofiler workflows. The reference nextflow command from that note was:

```bash
nextflow run epi2me-labs/wf-metagenomics \
  --fastq '/mnt/c/data/<run_path>/fastq_pass/' \
  --database_set 'SILVA_138_1' \
  --out_dir '/mnt/c/.../nanopore_processed/outputs_wf_metagenomics_ssu/<run_accession>'
```

Key design decisions recorded in that note:
- The SSU script uses the same `epi2me-labs/wf-metagenomics` pipeline as the AMR script, with `--database_set SILVA_138_1` for 16S/18S rRNA classification instead of the CARD database.
- Unlike `start_nextflow.sh` (taxprofiler), the SSU script does not require a `databases.csv` or an `all_samples_*.csv` samplesheet.
- Output lands in `nanopore_processed/outputs_wf_metagenomics_ssu/`, parallel to the taxprofiler and AMR output directories.
