# start_biomeme.sh

This script processes Biomeme qPCR assay results for the ODIN eDNA analysis workflow.

## Overview

The script traverses Biomeme qPCR Excel files, extracts Cq (cycle quantification) values, calculates pathogen abundance using assay parameters, applies quality flagging, and outputs processed datasets for Enlighten visualization.

## Usage

```bash
start_biomeme.sh [biomeme_data_path] [metadata_file]
```

The script will prompt you for:
- The Biomeme data path (`biomeme_data_path`) — **Folder containing a `biomeme_input_data/` subfolder** with qPCR Excel files
- The path to the metadata Excel file (`metadata_file`)

It will use cached values from your user config at `~/.odin_ml/odin_paths.txt` if you just press enter at the prompt.

## Arguments

- `biomeme_data_path`: Folder containing Biomeme qPCR results. Must have a `biomeme_input_data/` subfolder with Excel files organized by country code and sampling date.
- `metadata_file`: Path to the metadata Excel file (must contain `biomeme`, `sites`, and `samples` sheets).

## Workflow

1. Validates the `biomeme_input_data/` subfolder exists in the data path.
2. Reads metadata from Excel (biomeme and sites sheets).
3. Traverses the directory structure: `biomeme_input_data/{country_code}/{sampling_date}/`.
4. For each qPCR Excel file:
   - Extracts Cq values from worksheet rows.
   - Merges with assay parameters from `config/assay-params.csv` (slope, intercept, efficiency per pathogen).
   - Calculates abundance: `Abundance = 10^((Cq - B) / M)`.
   - Applies quality flags (0–4) and determines presence (`true`, `true_x`, `false`).
5. Enriches data with site metadata (country, coordinates).
6. Outputs processed results as Feather for Enlighten and Excel for review.

## Output

- `{biomeme_data_path}/biomeme_processed/BiomemeAssay.xlsx` — Excel for manual review
- `{enlighten_data_path}/BiomemeAssay.feather` — Feather for Enlighten visualization

## See Also

- [Biomeme Processing Details](biomeme_processing.md) — Quality flag and presence column logic
- [Run Scripts Guide](run_scripts_guide.md)

### Using Configuration Values

If you've run other pipeline scripts before, the script will use saved paths from previous runs as defaults.
The paths are stored in your user config at `~/.odin_ml/odin_paths.txt`. You can edit this file to change your defaults. For new installations, the default config is `scripts/odin_paths.txt`.
