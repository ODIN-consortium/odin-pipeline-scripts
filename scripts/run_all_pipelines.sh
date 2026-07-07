#!/usr/bin/env bash
# =============================================================================
# run_all_pipelines.sh
# Batch-process all Nanopore runs through the taxprofiler and/or AMR pipelines,
# auto-merging runs that share the same sample_id/sampling_date/barcode.
#
# Usage:
#   ./run_all_pipelines.sh [OPTIONS]
#
# Required options:
#   -m, --minknow-data-dir DIR    Directory containing MinKNOW output folders
#   -o, --output-dir DIR          Root output directory
#   -x, --metadata-file FILE      Path to metadata Excel file
#
# Optional options:
#   -d, --databases-file FILE     Path to databases.csv
#   -v, --venv-folder DIR         Path to Python virtual environment
#   -k, --database DIR            Path to a local Kraken2 database directory for the AMR pipeline.
#                                  Passed as --database to wf-metagenomics, overriding the S3 download
#                                  while still using --database_set for parameter validation.
#   --exclude PATTERN            Comma-separated list of substrings — any run whose path contains
#                                  one of these strings will be skipped (e.g. --exclude Lib2BF_ODIN)
#   --force                       Overwrite existing Nextflow output directories (passed through to
#                                  start_nextflow.sh / start_nextflow_amr.sh)
#   --skip-existing               Skip runs whose Nextflow output directory already exists and is not
#                                  empty — allows resuming a batch from where it left off
#   --taxprofiler                 Run only the taxprofiler pipeline
#   --amr                         Run only the AMR pipeline
#   --both                        Run both pipelines (default)
#   --dry-run                     Print run groups without executing
#   -h, --help                    Display this help message and exit
#
# How it works:
#   1. Calls list_run_groups.py to discover all run_accessions present in
#      minknow_data_dir and group them by merge relationships from the metadata.
#   2. For each group, picks one representative run_accession and calls
#      start_nextflow.sh / start_nextflow_amr.sh with --auto-merge, so that
#      all runs in the group are concatenated and processed as a single job.
#   3. Runs that share a merge group are processed once only — the member runs are
#      skipped automatically because --auto-merge pulls them in via the representative.
#
# Pipeline failures are logged and do not abort the batch — processing continues
# with the next run_accession. A summary is printed at the end.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pre-declare variables that config_utils.sh checks with [ -z ] — required because
# this script runs with set -u (unbound variables are errors).
USER_CONFIG="${USER_CONFIG:-}"
DEFAULT_CONFIG="${DEFAULT_CONFIG:-}"
OLD_CONFIG="${OLD_CONFIG:-}"

source "${SCRIPT_DIR}/config_utils.sh"

# ── Defaults ──────────────────────────────────────────────────────────────────
RUN_TAXPROFILER=true
RUN_AMR=true
DRY_RUN=false
minknow_data_dir=""
output_dir=""
metadata_file=""
databases_file=""
venv_folder=""
database=""
FORCE=false
SKIP_EXISTING=false
EXCLUDE_PATTERNS=""

# Load cached defaults from user/default config so batch runs stay non-interactive.
if [[ -f "${USER_CONFIG}" ]]; then
    CONFIG_FILE="${USER_CONFIG}"
else
    CONFIG_FILE="${DEFAULT_CONFIG}"
fi
[[ -f "${CONFIG_FILE}" ]] && source "${CONFIG_FILE}"
fallback_to_default_config databases_file
fallback_to_default_config venv_folder
# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--minknow-data-dir) minknow_data_dir="$2"; shift 2 ;;
        -o|--output-dir)       output_dir="$2";       shift 2 ;;
        -x|--metadata-file)    metadata_file="$2";    shift 2 ;;
        -d|--databases-file)   databases_file="$2";   shift 2 ;;
        -v|--venv-folder)      venv_folder="$2";      shift 2 ;;
        -k|--database)         database="$2";         shift 2 ;;
        --force)               FORCE=true;                  shift ;;
        --skip-existing)       SKIP_EXISTING=true;          shift ;;
        --exclude)             EXCLUDE_PATTERNS="$2";      shift 2 ;;
        --taxprofiler) RUN_TAXPROFILER=true;  RUN_AMR=false;  shift ;;
        --amr)         RUN_TAXPROFILER=false; RUN_AMR=true;   shift ;;
        --both)        RUN_TAXPROFILER=true;  RUN_AMR=true;   shift ;;
        --dry-run)     DRY_RUN=true;                          shift ;;
        -h|--help)
            sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown option: $1"; echo "Run with --help for usage."; exit 1 ;;
    esac
done

# ── Validate required arguments ───────────────────────────────────────────────
if [[ -z "$minknow_data_dir" || -z "$output_dir" || -z "$metadata_file" ]]; then
    echo "Error: minknow_data_dir, output_dir, and metadata_file are required."
    echo "Run with --help for usage."
    exit 1
fi

if $RUN_TAXPROFILER && [[ -z "${databases_file}" ]]; then
    echo "Error: databases_file is required for taxprofiler in batch mode."
    echo "Provide -d/--databases-file or set databases_file in ${CONFIG_FILE}."
    exit 1
fi

if [[ ! -d "$minknow_data_dir" ]]; then
    echo "Error: minknow_data_dir does not exist: $minknow_data_dir"
    exit 1
fi

if [[ ! -f "$metadata_file" ]]; then
    echo "Error: metadata_file not found: $metadata_file"
    exit 1
fi

# ── Setup virtual environment ─────────────────────────────────────────────────
venv_folder=$(setup_venv "${venv_folder}" "${venv_folder}")
activate_venv "${venv_folder}" || exit 1

# ── Set up log file ───────────────────────────────────────────────────────────
mkdir -p "${output_dir}"
LOG_FILE="${output_dir}/run_all_pipelines_$(date '+%Y%m%d_%H%M%S').log"
# Tee all subsequent stdout+stderr to the log file
exec > >(tee -a "$LOG_FILE") 2>&1
echo "Log file: $LOG_FILE"

# ── Discover run groups ───────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo " ODIN Batch Pipeline Runner"
echo " MinKNOW dir : $minknow_data_dir"
echo " Output dir  : $output_dir"
echo " Metadata    : $metadata_file"
echo " Taxprofiler : $RUN_TAXPROFILER"
echo " AMR         : $RUN_AMR"
echo " Dry run     : $DRY_RUN"
echo "=========================================="
echo ""
echo "Discovering run groups..."

LIST_RUN_GROUPS_SCRIPT="${SCRIPT_DIR}/list_run_groups.py"
mapfile -t RUN_REPRESENTATIVES < <(
    ${PYTHON_CMD} "${LIST_RUN_GROUPS_SCRIPT}" \
        --minknow_data_dir "${minknow_data_dir}" \
        --metadata_file "${metadata_file}" \
        2>&1 | tee /dev/stderr | grep -v '^#'
)

if [[ ${#RUN_REPRESENTATIVES[@]} -eq 0 ]]; then
    echo "No processable run_accessions found. Exiting."
    exit 1
fi

echo ""
echo "Found ${#RUN_REPRESENTATIVES[@]} run group(s) to process:"
for ra in "${RUN_REPRESENTATIVES[@]}"; do
    echo "  - $ra"
done
echo ""

if $DRY_RUN; then
    echo "Dry run — exiting without running any pipelines."
    exit 0
fi

# ── Process each run group ────────────────────────────────────────────────────
SUCCEEDED=()
FAILED_TAXPROFILER=()
FAILED_AMR=()

for RUN_ACCESSION_PATH in "${RUN_REPRESENTATIVES[@]}"; do
    echo ""
    echo "=========================================="
    echo " Processing: $RUN_ACCESSION_PATH"
    echo "=========================================="

    # Check --exclude patterns
    if [[ -n "${EXCLUDE_PATTERNS}" ]]; then
        IFS=',' read -ra _excl_list <<< "${EXCLUDE_PATTERNS}"
        _skip=false
        for _pat in "${_excl_list[@]}"; do
            if [[ "${RUN_ACCESSION_PATH}" == *"${_pat}"* ]]; then
                echo "Excluded by --exclude pattern '${_pat}' — skipping."
                _skip=true
                break
            fi
        done
        $_skip && continue
    fi

    # Prune stopped Docker containers and dangling images between runs to
    # release memory that Nextflow/Docker did not fully free after the previous run.
    if command -v docker &>/dev/null; then
        docker container prune -f &>/dev/null || true
    fi

    # ── Taxprofiler ──────────────────────────────────────────────────────
    if $RUN_TAXPROFILER; then
        echo ""
        echo "--- Taxprofiler ---"
        TAXPROFILER_ARGS=(
            --auto-merge
            "${minknow_data_dir}"
            "${output_dir}"
            "${RUN_ACCESSION_PATH}"
            "${metadata_file}"
            "${databases_file}"
            "${venv_folder}"
        )
        $FORCE && TAXPROFILER_ARGS+=(--force)
        $SKIP_EXISTING && TAXPROFILER_ARGS+=(--skip-existing)
        if bash "${SCRIPT_DIR}/start_nextflow.sh" "${TAXPROFILER_ARGS[@]}"; then
            echo "Taxprofiler: SUCCESS for $RUN_ACCESSION_PATH"
        else
            echo "Taxprofiler: FAILED for $RUN_ACCESSION_PATH"
            FAILED_TAXPROFILER+=("$RUN_ACCESSION_PATH")
        fi
    fi

    # ── AMR ──────────────────────────────────────────────────────────────
    if $RUN_AMR; then
        echo ""
        echo "--- AMR ---"
        AMR_ARGS=(
            --auto-merge
            "${minknow_data_dir}"
            "${output_dir}"
            "${RUN_ACCESSION_PATH}"
            "${metadata_file}"
            "${venv_folder}"
        )
        $FORCE && AMR_ARGS+=(--force)
        $SKIP_EXISTING && AMR_ARGS+=(--skip-existing)
        if [[ -n "${database}" ]]; then
            AMR_ARGS+=(--database "${database}")
        fi
        if bash "${SCRIPT_DIR}/start_nextflow_amr.sh" "${AMR_ARGS[@]}"; then
            echo "AMR: SUCCESS for $RUN_ACCESSION_PATH"
        else
            echo "AMR: FAILED for $RUN_ACCESSION_PATH"
            FAILED_AMR+=("$RUN_ACCESSION_PATH")
        fi
    fi

    # Track overall success (succeeds if all enabled pipelines succeeded)
    if { ! $RUN_TAXPROFILER || [[ ! " ${FAILED_TAXPROFILER[*]} " == *" $RUN_ACCESSION_PATH "* ]]; } && \
       { ! $RUN_AMR        || [[ ! " ${FAILED_AMR[*]} "         == *" $RUN_ACCESSION_PATH "* ]]; }; then
        SUCCEEDED+=("$RUN_ACCESSION_PATH")
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo " Batch run complete"
echo "=========================================="
echo " Succeeded : ${#SUCCEEDED[@]} / ${#RUN_REPRESENTATIVES[@]}"

if [[ ${#FAILED_TAXPROFILER[@]} -gt 0 ]]; then
    echo " Taxprofiler failures:"
    for f in "${FAILED_TAXPROFILER[@]}"; do echo "   - $f"; done
fi

if [[ ${#FAILED_AMR[@]} -gt 0 ]]; then
    echo " AMR failures:"
    for f in "${FAILED_AMR[@]}"; do echo "   - $f"; done
fi

TOTAL_FAILED=$(( ${#FAILED_TAXPROFILER[@]} + ${#FAILED_AMR[@]} ))
echo "=========================================="
echo ""

[[ $TOTAL_FAILED -gt 0 ]] && exit 1 || exit 0
