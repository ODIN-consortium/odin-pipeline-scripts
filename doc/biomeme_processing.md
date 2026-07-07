# Biomeme qPCR Data Processing

This document describes the workflow and logic implemented in `decode.py` for processing Biomeme qPCR data, with a focus on the interpretation of quality flags.

## Overview

The `decode.py` script extracts, merges, and analyzes qPCR results from Biomeme Excel files. It calculates abundance values, merges with metadata and assay parameters, and assigns quality flags to each measurement to indicate data reliability.

## Workflow Steps

1. **Extract Data**: Reads Excel files, extracting well numbers, sample IDs, fluorophores, target IDs, and Cq values.
2. **Merge Metadata**: Combines extracted data with run metadata and assay parameters.
3. **Calculate Abundance**: Uses assay parameters to compute abundance and diluted abundance for each measurement.
4. **Assign Quality Flags**: Flags each result based on replicate consistency and NTC thresholds.

## Quality Flag Descriptions

Each measurement receives a `quality_flag` value indicating its reliability:

| Flag Value | Meaning                                                                                 |
|------------|----------------------------------------------------------------------------------------|
| 0          | Not checked (default, before flagging logic is applied)                                |
| 1          | **Good**: More than one non-zero Cq value for the replicate/target combination         |
| 2          | **Questionable**: Only one non-zero Cq value for the replicate/target combination      |
| 3          | **Bad**: Cq value is zero (no amplification detected)                                  |
| 4          | **Below NTC threshold**: Cq value is below the NTC (No Template Control) threshold for matching fluorophore and target ID |

## Presence Column Logic

The `presence` column is included in the output dataset after processing. It is derived from the `quality_flag` and the mean abundance for each measurement:

- `true`: Assigned if `quality_flag` is **1 (Good)** and mean abundance is greater than 0.
- `true_x`: Assigned if `quality_flag` is **2 (Questionable)** and mean abundance is greater than 0.
- `false`: Assigned for all other combinations (including Bad, Below NTC threshold, or mean abundance ≤ 0).

This logic allows users to distinguish between highly reliable detections (`true`), less reliable detections (`true_x`), and negative or unreliable results (`false`).

The `presence` column is intended for downstream filtering and interpretation, enabling users to quickly identify which measurements indicate the presence of a target organism with varying levels of confidence.

### NTC Threshold Logic

- If a sample's "Biomeme replicate" contains "NTC" (case-insensitive) and its Cq is non-zero, this Cq value is used as a threshold.
- Any non-NTC sample with the same fluorophore and target ID, and a Cq value below this threshold, is flagged as `4` (Below NTC threshold).

## Output

The processed data includes:

- Sample and assay information
- Calculated abundance values
- Quality flags for each measurement
- **Presence column**: Indicates detection reliability and is suitable for downstream filtering and interpretation

This enables downstream filtering and interpretation of qPCR results based on data quality and detection reliability.

## References

- Script: [`decode.py`](../scripts/decode.py)
- Assay parameters: `config/assay-params.csv`
- Metadata: User-provided Excel file
