# FASTQ Concatenation Script

## Overview

The `concatenate_fastq_by_sample.py` script merges FASTQ files from multiple sequencing runs that belong to the same sample. This is essential when a sample has been sequenced across multiple runs and the data needs to be combined for downstream analysis. The script intelligently locates raw FASTQ files from MinKNOW output directories and concatenates them by barcode, ensuring data consistency through metadata validation.

## Input Arguments

### Required Arguments

- `--minknow_data_dir` (required): Root directory containing MinKNOW output folders with raw sequencing data
- `--output_dir` (required): Root output directory (currently unused but kept for compatibility with bash wrapper scripts)
- `--metadata_file` (required): Path to the metadata Excel file that defines sample information and run relationships
- `--tmp_dir` (required): Temporary directory where concatenated FASTQ files will be saved

### Mutually Exclusive Identifiers (choose one)

- `--run_accession <run_accession>`: Process a specific run accession (with optional merging of connected runs)
- `--sample_id <sample_id>`: Process all run accessions associated with a specific sample ID

## Logic for Finding Connected Run Accessions

The script uses the same connection logic as the AMR parser to identify related sequencing runs:

### When Using `--run_accession`

1. **Check metadata for connections**: The script identifies connected runs by matching three criteria:
   - Same `sample_id` (e.g., "SITE01_WW_001")
   - Same `sampling_date` (samples collected on the same day)
   - Same `barcode` (same barcode used during sequencing)
   
   All three must match for runs to be considered connected.

2. **Interactive user prompt**: If connected runs are found, the script displays a table showing:
   - `sampleName`: The sample name in the directory structure
   - `sample_id`: Sample identifier from metadata
   - `sampling_date`: Date the sample was collected
   - `barcode`: Barcode used (e.g., barcode01, barcode02)
   - `run_accession`: Run identifier
   
   The user is then prompted to choose:
   - **Option 1**: Concatenate FASTQ files from ALL related run_accessions
   - **Option 2**: Concatenate FASTQ files from ONLY the provided run_accession

3. **Validation**: If merging multiple runs, the script validates that:
   - Each barcode has consistent `sample_id`, `sampling_date`, and `sampleName` across all runs
   - No other unexpected run_accessions are associated with the same barcode

### When Using `--sample_id`

1. **Automatic selection**: The script automatically finds all run_accessions with the matching `sample_id`
2. **Barcode grouping**: For each barcode found, the script groups runs and validates consistency
3. **No user prompt**: Processing proceeds automatically without user interaction

## Directory Discovery Process

The script follows this process to locate FASTQ files:

1. **Search MinKNOW directory structure**: 
   - Recursively searches `minknow_data_dir` for directories matching each `run_accession`
   - Looks for `fastq_pass` subdirectories containing raw sequencing data

2. **Directory structure example**:
   ```
   minknow_data_dir/
   ├── experiment_name/
   │   ├── sampleName_or_run_id/
   │   │   ├── run_accession/
   │   │   │   ├── fastq_pass/
   │   │   │   │   ├── barcode01/
   │   │   │   │   │   ├── file001.fastq.gz
   │   │   │   │   │   ├── file002.fastq.gz
   │   │   │   │   │   └── ...
   │   │   │   │   ├── barcode02/
   │   │   │   │   └── ...
   ```

3. **Barcode filtering**: Only barcodes present in the metadata are processed

## File Concatenation Process

### How Files Are Combined

1. **Barcode-by-barcode processing**: For each barcode in the metadata:
   - Collects all `.fastq.gz` files from the barcode directory across all selected run_accessions
   - Sorts files alphabetically for consistent ordering
   - Concatenates files in binary mode using 8 MB chunks for efficiency

2. **File naming convention**:
   - **Single run**: `{barcode}_{run_accession}.fastq.gz`
   - **Multiple runs**: `{barcode}_{sampleName}.fastq.gz` or `{barcode}_merged_{first_run_accession}.fastq.gz`

3. **Output structure**:
   ```
   tmp_dir/
   ├── barcode01/
   │   └── barcode01_sampleName.fastq.gz
   ├── barcode02/
   │   └── barcode02_sampleName.fastq.gz
   └── .fastq_identifier  # Contains the identifier used for naming
   ```

### Binary Concatenation

The script uses efficient binary file concatenation:
- Files are copied in 8 MB chunks to manage memory efficiently
- Gzip compression is preserved (no decompression/recompression)
- Original FASTQ files remain unchanged in their source locations

## Output Files

The script generates:

1. **Concatenated FASTQ files**: One file per barcode, organized in subdirectories
   - Location: `tmp_dir/{barcode}/{barcode}_{identifier}.fastq.gz`
   - Format: Gzip-compressed FASTQ format

2. **Identifier file**: Hidden file for bash script integration
   - Location: `tmp_dir/.fastq_identifier`
   - Contains: The identifier used for naming (sampleName, merged_runID, or run_accession)

## Example Usage

### Concatenate by Run Accession (with interactive prompt)

```bash
python scripts/concatenate_fastq_by_sample.py \
  --minknow_data_dir /path/to/minknow/data \
  --output_dir /path/to/output \
  --run_accession ERR123456 \
  --metadata_file metadata/nanopore_samples.xlsx \
  --tmp_dir /tmp/concatenated_fastq
```

**Interactive prompt example**:
```
You provided run_accession: ERR123456

Found the following run_accessions with matching sample_id and sampling_date:
========================================================================================================================
sampleName                sample_id                 sampling_date  barcode     run_accession                           
------------------------------------------------------------------------------------------------------------------------
SITE01_WW_001_20250115   SITE01_WW_001             2025-01-15     barcode01   ERR123456                               
SITE01_WW_001_20250115   SITE01_WW_001             2025-01-15     barcode01   ERR123457                               
SITE01_WW_001_20250115   SITE01_WW_001             2025-01-15     barcode02   ERR123456                               
SITE01_WW_001_20250115   SITE01_WW_001             2025-01-15     barcode02   ERR123457                               
========================================================================================================================
Do you want to:
1. Concatenate fastq files from ALL related run_accessions shown above
2. Concatenate fastq files from ONLY the provided run_accession
Enter your choice (1 or 2): 
```

### Concatenate by Sample ID (automatic)

```bash
python scripts/concatenate_fastq_by_sample.py \
  --minknow_data_dir /path/to/minknow/data \
  --output_dir /path/to/output \
  --sample_id SITE01_WW_001 \
  --metadata_file metadata/nanopore_samples.xlsx \
  --tmp_dir /tmp/concatenated_fastq
```

## Logging and Output Messages

The script provides color-coded logging:

- **INFO** (white): Normal processing information
- **WARNING** (yellow): Non-critical issues (e.g., missing directories, no files found)
- **ERROR** (red): Critical errors that stop execution

### Common Log Messages

**Success messages**:
```
INFO - Found 2 run_accessions for run_accession 'ERR123456': ['ERR123456', 'ERR123457']
INFO - Found 2 valid barcodes: ['barcode01', 'barcode02']
INFO - Found fastq_pass for ERR123456: /path/to/fastq_pass
INFO - Concatenating 150 files for barcode01
INFO - Successfully created 2 concatenated files:
INFO -   barcode01: /tmp/concatenated_fastq/barcode01/barcode01_SITE01_WW_001_20250115.fastq.gz
```

**Warning messages**:
```
WARNING - No fastq_pass directory found for run_accession: ERR123458
WARNING - No fastq.gz files found in /path/to/barcode03
WARNING - Barcode 'barcode05' is associated with run_accessions {'ERR999999'} not in the selected set
```

**Error messages**:
```
ERROR - No metadata found for run_accession: ERR999999
ERROR - Inconsistent metadata for barcode 'barcode01': sample_ids=['SITE01_WW_001', 'SITE02_WW_002']
ERROR - MinKNOW data directory not found: /invalid/path
```

## Data Flow

1. **Parse command-line arguments**: Determine whether processing by run_accession or sample_id
2. **Read and validate metadata**: 
   - Load metadata Excel file
   - Filter to rows with valid run_accession, barcode, sample_id, and sampling_date
3. **Find connected runs** (if using --run_accession):
   - Identify runs with matching sample_id + sampling_date + barcode
   - Display interactive table and prompt user for choice
4. **Validate consistency**:
   - Group by barcode
   - Ensure each barcode has consistent sample_id, sampling_date, and sampleName
5. **Discover FASTQ directories**:
   - Search MinKNOW directory structure for each run_accession
   - Locate fastq_pass subdirectories
6. **Concatenate files**:
   - For each barcode, collect all .fastq.gz files across selected runs
   - Sort files and concatenate in 8 MB chunks
   - Save to tmp_dir with appropriate naming
7. **Write identifier file**: Save naming identifier for downstream processing
8. **Report results**: Display summary of created files

## Error Handling and Validation

### Metadata Validation

- **Missing required fields**: Script exits if run_accession, barcode, sample_id, or sampling_date are missing
- **Inconsistent barcode metadata**: Script exits if the same barcode has different sample_ids, dates, or names across runs
- **Unknown identifiers**: Script exits if the provided run_accession or sample_id is not found in metadata

### File System Validation

- **Missing directories**: Warnings logged, processing continues with available data
- **No FASTQ files found**: Warnings logged for each barcode with missing data
- **Failed concatenation**: Errors logged, processing continues with remaining barcodes

### Exit Conditions

The script exits with error code 1 if:
- No metadata found for the specified identifier
- Inconsistent metadata detected for any barcode
- Required directories (minknow_data_dir, metadata_file) don't exist
- No fastq_pass directories found for any run_accession
- No files were successfully concatenated

## Integration with Pipeline

This script is typically called by bash wrapper scripts that:
1. Call `concatenate_fastq_by_sample.py` to merge FASTQ files
2. Read the `.fastq_identifier` file to determine the output naming
3. Pass concatenated files to downstream analysis pipelines (e.g., Nextflow workflows)

The `--output_dir` parameter is kept for compatibility with these wrapper scripts but is not currently used by the Python script itself.

## Performance Considerations

- **Memory efficiency**: Uses 8 MB chunk size for file copying to handle large files
- **Disk I/O**: Binary concatenation is faster than decompression/recompression
- **Sorting**: Files are sorted alphabetically to ensure consistent, reproducible output
- **Scalability**: Can handle hundreds of FASTQ files per barcode across multiple runs

