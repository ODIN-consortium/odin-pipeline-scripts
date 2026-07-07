# Running Bash Scripts in the `scripts` Folder

## Prerequisites

- Ensure you are using Ubuntu (WSL or native, see the [setup guide](setup_mobile_lab_computer.md)).
- Python virtual environment with dependencies from `requirements.txt` installed.
- Nextflow installed and in your PATH.
- Docker installed and running (post-installation steps completed for non-root usage).
- A directory with MinKNOW output containing `fastq_pass` folders with barcode subdirectories.
- A metadata Excel file (`.xlsx`) with `nanopore` and `sites` sheets.
- Sufficient disk space for the analysis output.

## Configuration

All scripts read paths from a configuration file. On first run, each script will prompt for required paths and save them for future use.

**Config file priority:**
1. `~/.odin_ml/odin_paths.txt` — User override (created after first run)
2. `scripts/odin_paths.txt` — Default (checked into repo)

You can edit `~/.odin_ml/odin_paths.txt` directly to change defaults.

## Adding Scripts to PATH

```bash
export PATH="$PATH:$HOME/pipeline_scripts/scripts"
```

Add this line to your `.bashrc` or `.zshrc` to make it permanent.

## Typical Workflows

### Taxonomic Profiling (Most Common)

```bash
# Run the taxprofiler pipeline — prompts for all inputs
./scripts/start_nextflow.sh

# Then start Enlighten to view results
./scripts/start_enlighten.sh
```

### AMR Detection

```bash
# Run AMR analysis
./scripts/start_nextflow_amr.sh

# Parse AMR JSON results into tabular format
./scripts/parse_amr_json.sh
```

### Biomeme qPCR Processing

```bash
# Process Biomeme qPCR data
./scripts/start_biomeme.sh

# Start Enlighten to view results
./scripts/start_enlighten.sh
```

### Mpox Analysis

```bash
# Run Mpox consensus + phylogenetics (requires squirrel conda environment)
./scripts/start_mpox.sh
```

### System Validation

```bash
# Check environment integrity (Python, Nextflow, Docker, paths)
./scripts/integrity_check.sh

# Verify metadata matches MinKNOW directory structure
./scripts/verify_metadata.sh
```

## Pipeline Scripts Documentation

- [start_nextflow.sh - Taxprofiler Pipeline](./start_nextflow.md)
- [start_nextflow_amr.sh - AMR Detection Pipeline](./start_nextflow_amr.md)
- [start_nextflow_ssu.sh - SSU rRNA Analysis Pipeline](./start_nextflow_ssu.md)
- [start_biomeme.sh - Biomeme qPCR Pipeline](./start_biomeme.md)
- [start_mpox.sh - Mpox Pipeline](./start_mpox.md)
- [start_enlighten.sh - Enlighten Visualization](./start_enlighten.md)