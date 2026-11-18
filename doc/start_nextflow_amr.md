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

- **Database Set**: PlusPF-8 (optimized for pathogen identification), used only when no local Kraken2 database applies (see below)
- **AMR Database**: card (Comprehensive Antibiotic Resistance Database)

## Kraken2 database for the classification step

The AMR genes come from abricate against CARD. The Kraken2 step of wf-metagenomics only gives the per-barcode read totals in `amr_data.feather`, so using the Kraken2 database taxprofiler uses keeps `classified_reads` comparable with the taxonomy datasets. The ODIN custom database v6 is the one the published AMR results used.

The database is chosen in this order:

1. `--database PATH`, where `PATH` is a database directory, or `download` for the downloaded `database_set`.
2. `kraken2_db_amr` in the config file (same values).
3. The `kraken2` row of `databases.csv` (the `databases_file` setting) whose directory has a Bracken file. Two such rows stop the run; name one with option 1 or 2.
4. Otherwise wf-metagenomics downloads the `database_set`.

wf-metagenomics refuses a database directory without a Bracken `database<length>mers.kmer_distrib` file, so the script checks for it, and that the directory exists, before the FASTQ files are concatenated. The command then gets `--database <dir>` (with `--database_set`, which wf-metagenomics still validates) and, when `<dir>/taxonomy` has `names.dmp` and `nodes.dmp`, `--taxonomy <dir>/taxonomy`. Without `--taxonomy` wf-metagenomics uses its own NCBI taxonomy, which may not resolve the custom taxids of the ODIN database the same way. The chosen database is printed at the start of the run.

## Replicates

Barcodes numbered as replicates of one sample (the `replicate` column of the `nanopore` sheet) are pooled
into one input before screening, as odin_pipeline does by default; the output then has `barcode14-barcode17`
where it would have had `barcode14` and `barcode17`. See `doc/README_CONCATENATE_FASTQ.md`.

- `--amr-replicates pool|per_barcode` (or `amr_replicates` in the config file) chooses. The default is
  `pool`. `per_barcode` screens each barcode and keeps its replicate number (odin_pipeline's
  `amr_replicates = per_barcode`).
- Give `parse_amr_json.sh` the same value (`-r`, or the same `amr_replicates` config setting): it has to
  read the output the way the run wrote it.
- A group that cannot be pooled (unnumbered, partly numbered, repeated numbers) stops the run before any
  FASTQ file is written.

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

The choice of `epi2me-labs/wf-metagenomics` for AMR detection was specified by the WP3 bioinformatics team in August 2025, when the three analysis workflows and their output directory structure were also defined. The reference nextflow command was:

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
- Unlike `start_nextflow.sh` (taxprofiler), neither the AMR nor the SSU script requires a `databases.csv` or an `all_samples_*.csv` samplesheet. The AMR script reads `databases.csv`, when there is one, only to find the local Kraken2 database (see above); that database was added after this note.
- Output lands in `nanopore_processed/outputs_wf_metagenomics_amr/` (AMR) and `nanopore_processed/outputs_wf_metagenomics_ssu/` (SSU), parallel to the taxprofiler output directory.
