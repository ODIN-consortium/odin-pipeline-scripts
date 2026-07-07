# start_mpox.sh

`start_mpox.sh` is a Bash script that automates the setup and execution of the artic-mpxv-nf Nextflow pipeline for processing MinKNOW nanopore sequencing data for Mpox (Monkeypox virus). It also runs downstream phylogenetic analysis using the `squirrel` tool.

## Purpose

- Collects user input and configuration for pipeline execution.
- Prepares necessary directories and configuration files.
- Generates a sample sheet CSV for the pipeline.
- Runs the artic-mpxv-nf Nextflow workflow.
- Executes squirrel for phylogenetic analysis on pipeline results.

## Usage

```bash
./start_mpox.sh [minknow_data_dir] [output_dir] [run_accession]
```

- `minknow_data_dir`: Directory containing MinKNOW output folders.
- `output_dir`: Root directory for output data.
- `run_accession`: Path to run accession (runName/sampleName/run_accession) within `minknow_data_dir`.

Use `-h` or `--help` for usage instructions.

## Workflow Steps

1. **Configuration Loading**: Loads default and user-specified paths from your user config at `~/.odin_ml/odin_paths.txt` (or the default `scripts/odin_paths.txt` if not present) and sources utility functions from `config_utils.sh`.
2. **User Prompts**: Asks for required directories, metadata file, clade, and scheme version.
3. **Directory Preparation**: Ensures output directories exist and are ready for pipeline results.
4. **Sample Sheet Creation**: Runs `create_mpox_samples_csv.py` to generate a sample sheet CSV. Requires a `type` column in metadata with values: `test_sample`, `positive_control`, `negative_control`, `no_template_control`.
5. **Pipeline Execution**: Runs the artic-mpxv-nf Nextflow workflow with specified parameters.
6. **Phylogenetic Analysis**: Activates the `squirrel` conda environment and runs squirrel on pipeline consensus sequences with `--run-apobec3-phylo --include-background`.

## Clade and Scheme Selection

The script prompts for clade and scheme version interactively:

**Available clades:** `cladei`, `cladeia`, `cladeib`, `cladeii`, `cladeiia`, `cladeiib`

**Available scheme versions:**
- `yale-mpox/2000/v1.0.0-cladei`
- `yale-mpox/2000/v1.0.0-cladeii`
- `artic-inrb-mpox/2500/v1.0.0`

## Output

- Nextflow results: `nanopore_processed/outputs_wf_artic-mpxv-nf/{run_accession}/`
- Squirrel phylogenetic results: `nanopore_processed/output_squirrel/{run_accession}/`

## Requirements

- Bash shell
- Nextflow
- Python (with required dependencies)
- Conda (for squirrel)
- MinKNOW output data
- Configuration files: `~/.odin_ml/odin_paths.txt` (user), `scripts/odin_paths.txt` (default), `config_utils.sh`, `create_mpox_samples_csv.py`

## Example

```bash
./start_mpox.sh /mnt/c/Users/odin-/Documents/mock_MinKNOW_output_folder/ /mnt/c/Users/odin-/Documents/ODIN/data runName/sampleName/run_accession
```

## Notes

- The script will prompt for missing arguments and choices interactively.
- Errors during execution will be reported, and the script will exit on failure.
