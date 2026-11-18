# Biomeme qPCR Data Processing

This document describes the workflow and logic implemented in `decode.py` for processing Biomeme qPCR data, with a focus on the interpretation of quality flags.

## Overview

The `decode.py` script extracts, merges, and analyzes qPCR results from Biomeme Excel files. It calculates abundance values, merges with metadata and assay parameters, and assigns quality flags to each measurement to indicate data reliability.

## Workflow Steps

1. **Extract Data**: Reads Excel files, extracting well numbers, sample IDs, fluorophores, target IDs, and Cq values.
2. **Merge Metadata**: Combines extracted data with run metadata and assay parameters.
3. **Calculate Abundance**: Uses assay parameters to compute abundance and diluted abundance for each measurement.
4. **Assign Quality Flags**: Flags each result based on replicate consistency and NTC thresholds.

## Grouping wells into samples

Each row of the `biomeme` metadata sheet describes one sample in one qPCR run
(`biomeme_run_name`). Its `Biomeme_sample_ID` is the comma-separated list of **well
labels** in that run's Excel file that belong to the sample — the numbered replicate
wells plus the run's no-template control(s), e.g. `5,6,NTC` or `3,4,NTC1,NTC2`.

Two rules follow from this, both enforced in `decode.py` since September 2026:

- **The lookup is built per run.** Well labels (`1`…`8`, `NTC`…) are reused in every
  run, so the well → sample map is built only from the metadata rows whose
  `biomeme_run_name` matches the sheet being processed. (Before the fix the map was built
  across all rows, so the *last* row containing e.g. `5` decided which wells `5` was
  grouped with; in the June 2026 dataset 11 of 97 positive sample × assay groups carried
  another sample's mean abundance.) A numbered label listed in two rows of the *same* run
  is a metadata error and stops processing with a `ValueError`; NTC labels are shared by
  every sample in a run and are exempt.
- **Control wells are not replicates.** The no-template controls (`NTC`, `NTC1`, …) and
  the positive control (`POS` / `Pos`) are listed in every sample's group but are
  excluded from `Mean Abundance` and from the replicate count that sets the quality flag;
  an amplifying NTC contributes to the NTC-threshold rule below, never to a sample's
  abundance. Labels are matched case-insensitively on the substrings `NTC` and `POS`.

## Control wells in the output

A control well is a property of the **run**, not of a sample. Since 23 September 2026
(pipeline_scripts, odin_pipeline v1.0.29) the output holds **one row per physical control well
per run**, marked `is_control = true`:

- `sample_code`, `Biomeme_sample_ID` and `dilution_factor` are empty on control rows. The row
  carries the run-level metadata that every sample of the run agrees on (run name, sampling
  date, country…) and nothing sample-level, even when the run holds a single sample.
- Every control well in the run file is written, **whether or not any sample's
  `Biomeme_sample_ID` lists it**, and the processing log warns about the unlisted ones
  (`WARNING: run …: control wells ['NTC3'] are not in any sample's Biomeme_sample_ID; kept as
  control rows`). Numbered wells that no sample lists are dropped, with a warning.
- Control rows keep their `Cq`; `Abundance`, `Abundance diluted`, `Mean Abundance`,
  `log1pMeanAbundance` and `presence` are empty. `quality_flag` is `3` when the control did not
  amplify and `0` (not scored) otherwise — the replicate flags describe a sample's wells.
- A run the metadata does not know (no `biomeme_run_name` rows) yields no rows at all, controls
  included.

Sample rows are therefore `is_control == false`, equivalently `presence.notna()`.

Before this change a control was copied once per sample that listed it — in the September 2026
dataset 120 physical control wells became 367 rows — and a control no sample listed (a file's
`NTC3`, or `NTC` where the metadata said `NTC1,NTC2`; the positive control in most runs) was
applied by the NTC rule but missing from the output, so the dataset showed samples rejected for
a blank that was not there.

## Quality Flag Descriptions

Each measurement receives a `quality_flag` value indicating its reliability:

| Flag Value | Meaning                                                                                 |
|------------|----------------------------------------------------------------------------------------|
| 0          | Not checked (default, before flagging logic is applied)                                |
| 1          | **Good**: More than one non-zero Cq value for the replicate/target combination         |
| 2          | **Questionable**: Only one non-zero Cq value for the replicate/target combination      |
| 3          | **Bad**: Cq value is zero (no amplification detected)                                  |
| 4          | **Not distinguishable from the NTC**: the well amplified less than `NTC_MARGIN_CQ` (2) cycles before the run's strongest amplifying no-template control of the same fluorophore and target, or after it (Cq ≥ NTC Cq − 2) |
| 5          | **Excluded**: the lab declared this run's assay unreliable (`config/assay-exclusions.csv`, one row per run and target, `*` = every target of the run; e.g. primer/probe stocks contaminated with positive-control DNA). Whatever the well shows, it is neither a detection nor a negative — the result is unknown. The run's controls are reported as they are. |

### Controls the run file mislabelled

A control well counts as one because its label contains `NTC` or `POS`. When the operator forgot
to label the no-template control in the Biomeme app, the file calls it by a sample number (`9`) or
not at all, and the decoder sees no control: nothing sets the NTC floor and wells that amplified
together with the blank pass as positives. The raw export is not edited. Instead the metadata's
`Biomeme_sample_ID` names the control by its **well number**: `1,2,NTC@9` means "well 9 of the file
is a no-template control called NTC, whatever the file labels it". The relabelled well then behaves
like any control — it sets the floor, is written once per run with `is_control = true`, and is never
a replicate. A token that names a well also listed as a sample well, or that is malformed, is a
metadata error and stops the run. Added October 2026 for runs `2025-09-06-07380647` (NTC labelled
`9`) and `2025-09-13-05441615` (unlabelled well 7); logged as change group C19.

## Presence Column Logic

The `presence` column is included in the output dataset after processing. It is derived from the `quality_flag` and the mean abundance for each measurement:

- `true`: Assigned if `quality_flag` is **1 (Good)** and mean abundance is greater than 0.
- `true_x`: Assigned if `quality_flag` is **2 (Questionable)** and mean abundance is greater than 0.
- `false`: Assigned for all other combinations (including Bad, Below NTC threshold, Excluded, or mean abundance ≤ 0).

This logic allows users to distinguish between highly reliable detections (`true`), less reliable detections (`true_x`), and negative or unreliable results (`false`).

**Decision (22 September 2026):** wells rejected by the NTC rule (`quality_flag` 4)
keep `presence = false`; no separate value is introduced. The column exists so that the true
amplifications can be selected quickly — `true` for replicated detections, `true_x` (added so that
single-replicate successes are not lost) for one well — and a well that cannot be told from the
blank is, for that purpose, not a detection. Anyone who needs the distinction has `quality_flag`
(3 = no amplification, 4 = rejected by the NTC rule) on the same row. A richer selector may come
from the Enlighten side one day; the data contract stays as it is.

The `presence` column is intended for downstream filtering and interpretation, enabling users to quickly identify which measurements indicate the presence of a target organism with varying levels of confidence.

### Dilution factor

`dilution_factor` in the metadata (`biomeme_runs`) is the **fraction of the original sample
strength** that went into the reaction: `0.5` for a 1:2 dilution, `0.01` for 1/100. `Abundance
diluted` is the abundance **corrected back to the undiluted sample**:
`Abundance diluted = Abundance / dilution_factor` (a 1:2 dilution doubles the copies), applied
after the metadata merge; rows without a factor carry `Abundance` unchanged. `Mean Abundance` and
`log1pMeanAbundance` are computed from the reaction-level `Abundance`, not the corrected value.
Until 22 September 2026 the factor was looked for before the merge, so it was never applied and
the two columns were always equal; on 22–23 September it was briefly applied as a multiplication
(v1.0.26), corrected to a division in v1.0.27 following the column's definition in the project's
data dictionary ("corrected for any sample dilution applied before the reaction").

Two other conventions of the output, for readers of the feather: `Cq = 0` means the well ran
all cycles without crossing the threshold (no amplification) — filter with `Cq > 0`, never
average the raw column; and `log1pMeanAbundance` is `ln(Mean Abundance + 1)` (`numpy.log1p`),
not log10. The column was called `logMeanAbundance` until 23 September 2026; it was renamed
because that name reads as log10, and a consumer taking 9.06 as 10^9.06 (1.1 billion copies)
instead of e^9.06 − 1 (about 8,600) had no way to know. Datasets processed before that date
carry the old name; the Enlighten column tooltip states the convention either way.

### NTC rule

A no-template control that amplifies means the assay produces signal from nothing —
contamination or primer-dimer. Its Cq is the run's contamination floor for that fluorophore
and target, and a lower Cq means more template, so:

- For each run × fluorophore × target, the **lowest** Cq among the amplifying NTC wells
  (the strongest contamination) is the reference.
- A sample well is trusted only when it amplified at least `NTC_MARGIN_CQ` cycles **earlier**
  than that reference (Cq < NTC Cq − margin). Every other amplifying well of that fluorophore
  and target — within the margin, or later than the NTC — is flagged `4` and its `presence`
  is `false`.
- The margin defaults to 2 cycles, the criterion the lab applied when confirming positives
  ("greater than 2 Cq difference" kept, "within 1 Cq of NTC" rejected).
  Override with the environment variable `ODIN_NTC_MARGIN_CQ`.
- Wells of samples whose run has no amplifying NTC are not affected.

Until 22 September 2026 the comparison ran the other way (a well with Cq *below* the NTC Cq
was flagged), which rejected the strongest positives and kept wells weaker than the blank.
Datasets decoded before that date carry the old flag 4 and must be re-processed.

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
