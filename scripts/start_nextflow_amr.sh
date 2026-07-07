#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

VERIFY_PY_SCRIPT="${SCRIPT_DIR}/verify_nanopore_metadata.py"
CONCATENATE_FASTQ_SCRIPT="${SCRIPT_DIR}/concatenate_fastq_by_sample.py"

# Define pipeline_scripts folder (one level up from SCRIPT_DIR)
PIPELINE_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default paths
DEFAULT_MINKNOW_DATA_DIR="/mnt/c/data"
DEFAULT_OUTPUT_DIR="/mnt/c/Users/odin-/Documents/ODIN/data"
DEFAULT_DATABASE_SET="PlusPF-8"
DEFAULT_AMR_DB="card"
DEFAULT_METADATA_FILE="/mnt/c/Users/odin-/Documents/ODIN/data/metadata_DEPLOYMENT_2025.xlsx"

# Parse flags, collecting positional args separately
AUTO_MERGE=false
FORCE=false
SKIP_EXISTING=false
DATABASE_ARG=""
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)           echo "Usage: $0 [--auto-merge] [--force] [--skip-existing] [--database PATH] [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]"; exit 0 ;;
        --auto-merge)        AUTO_MERGE=true; shift ;;
        --force)             FORCE=true; shift ;;
        --skip-existing)     SKIP_EXISTING=true; shift ;;
        --database)          DATABASE_ARG="$2"; shift 2 ;;
        *)                   POSITIONAL_ARGS+=("$1"); shift ;;
    esac
done
set -- "${POSITIONAL_ARGS[@]:-}"

minknow_data_dir_arg="${1:-}"
output_dir_arg="${2:-}"
run_accession_arg="${3:-}"
metadata_file_arg="${4:-}"
venv_folder_arg="${5:-}"

[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config output_dir
fallback_to_default_config database_set
fallback_to_default_config amr_db
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder

# Set up virtual environment using shared function from config_utils.sh
venv_folder=$(setup_venv "${venv_folder_arg}" "${venv_folder:-$DEFAULT_VENV_DIR}")

# Get MinKNOW data directory
minknow_data_dir=$(get_path "Enter MinKNOW data directory" "${minknow_data_dir:-$DEFAULT_MINKNOW_DATA_DIR}" "${minknow_data_dir_arg}" "directory") || exit $?

# Get run accession using the common function
if ! get_run_accession "${minknow_data_dir}" "${run_accession_arg}"; then
    exit 1
fi

# Now use the exported environment variables
run_accession="${RUN_ACCESSION}"
runaccession_dir="${RUNACCESSION_DIR}"

# Get output directory
output_dir=$(get_path "Enter path to root output data directory" "${output_dir:-$DEFAULT_OUTPUT_DIR}" "${output_dir_arg}" "none") || exit $?
mkdir -p "${output_dir}"
output_dir_clean="${output_dir%/}"

metadata_file=$(get_path "Enter metadata file" "${metadata_file:-$DEFAULT_METADATA_FILE}" "${metadata_file_arg}" "file") || exit $?

# Save values to config file
# Note: run_accession is session-specific, not saved to config
set_config_value "${CONFIG_FILE}" minknow_data_dir "${minknow_data_dir}"
set_config_value "${CONFIG_FILE}" output_dir "${output_dir}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

# Verify metadata
py_verify_cmd="${PYTHON_CMD} \"${VERIFY_PY_SCRIPT}\" \"${minknow_data_dir}\" \"${metadata_file}\" \"${run_accession}\""
run_python_script "${py_verify_cmd}" || {
    echo -e "\n\033[0;31mMetadata verification failed. Exiting.\033[0m\n"
    exit 1
}
echo -e "\n\033[0;32mMetadata verification succeeded.\033[0m\n"

# Create temporary directory for input sequences
# Use $TMPDIR if set (to avoid filling tmpfs), otherwise fall back to /tmp
input_seqs_dir="$(mktemp -d "${TMPDIR:-/tmp}/input_seqs_${run_accession}_XXXXXX")"

# Resolve the file identifier from metadata (lightweight — no file I/O)
MERGE_FLAG=""
$AUTO_MERGE && MERGE_FLAG="--auto-merge"
resolve_cmd="${PYTHON_CMD} \"${CONCATENATE_FASTQ_SCRIPT}\" --minknow_data_dir \"${minknow_data_dir}\" --output_dir \"${output_dir_clean}\" --run_accession \"${run_accession}\" --metadata_file \"${metadata_file}\" --tmp_dir \"${input_seqs_dir}\" ${MERGE_FLAG} --resolve-identifier"
run_python_script "${resolve_cmd}" || {
    echo -e "\n\033[0;31mError: Failed to resolve identifier for run_accession ${run_accession}.\033[0m"
    rm -rf "${input_seqs_dir}"
    exit 1
}

# Read the identifier from the temporary file created by the Python script
identifier_file="${input_seqs_dir}/.fastq_identifier"
if [ -f "$identifier_file" ]; then
    file_identifier=$(cat "$identifier_file")
else
    # Fallback to run_accession if no identifier file was found
    file_identifier="$run_accession"
fi

echo -e "\nUsing identifier for output paths: ${file_identifier}"

# Set up output directory for wf-metagenomics_amr using file_identifier
nextflow_outdir=$(build_nextflow_outdir "${output_dir_clean}" "${file_identifier}" "nanopore_processed" "outputs_wf_metagenomics_amr")

# Prepare the output directory (ensures it exists and is empty)
FORCE_FLAG=""
$FORCE && FORCE_FLAG="force"
$SKIP_EXISTING && FORCE_FLAG="skip"
prepare_output_directory "${nextflow_outdir}" "Nextflow output directory" "${FORCE_FLAG}"
_pod_rc=$?
if [[ $_pod_rc -eq 2 ]]; then
    echo -e "\n\033[0;33mRun already processed — skipping.\033[0m\n"
    rm -rf "${input_seqs_dir}"
    exit 0
elif [[ $_pod_rc -ne 0 ]]; then
    rm -rf "${input_seqs_dir}"
    exit 1
fi

# Now do the actual concatenation (expensive — copies/merges fastq files)
concatenate_cmd="${PYTHON_CMD} \"${CONCATENATE_FASTQ_SCRIPT}\" --minknow_data_dir \"${minknow_data_dir}\" --output_dir \"${output_dir_clean}\" --run_accession \"${run_accession}\" --metadata_file \"${metadata_file}\" --tmp_dir \"${input_seqs_dir}\" ${MERGE_FLAG}"
run_python_script "${concatenate_cmd}" || {
    echo -e "\n\033[0;31mError: Failed to concatenate fastq files for run_accession ${run_accession}.\033[0m"
    rm -rf "${input_seqs_dir}"
    exit 1
}

# Nextflow arguments - use the temporary directory with barcode structure
fastq_dir="${input_seqs_dir}"
database_set="${database_set:-${DEFAULT_DATABASE_SET}}"
amr_db="${amr_db:-${DEFAULT_AMR_DB}}"

# Build nextflow command — when --database is set, pass it to wf-metagenomics to use a local
# Kraken2 database directory instead of downloading from S3. --database_set is still required
# to pass parameter validation, but --database overrides the actual database used.
if [[ -n "${DATABASE_ARG}" ]]; then
    nextflow_cmd="nextflow run -ansi-log false -with-trace \"${nextflow_outdir}/trace.txt\" -with-report \"${nextflow_outdir}/report.html\" -c \"${PIPELINE_SCRIPTS_DIR}/config/odin.config\" -profile epi2me epi2me-labs/wf-metagenomics --fastq \"${fastq_dir}\" --database_set \"${database_set}\" --database \"${DATABASE_ARG}\" --amr --amr_db \"${amr_db}\" --out_dir \"${nextflow_outdir}\""
else
    nextflow_cmd="nextflow run -ansi-log false -with-trace \"${nextflow_outdir}/trace.txt\" -with-report \"${nextflow_outdir}/report.html\" -c \"${PIPELINE_SCRIPTS_DIR}/config/odin.config\" -profile epi2me epi2me-labs/wf-metagenomics --fastq \"${fastq_dir}\" --database_set \"${database_set}\" --amr --amr_db \"${amr_db}\" --out_dir \"${nextflow_outdir}\""
fi
echo -e "\nRunning Nextflow command:\n"
echo "${nextflow_cmd}"
echo

if ! eval ${nextflow_cmd}; then
    echo -e "\n\033[0;31mError: Failed to run the Nextflow pipeline.\033[0m"
    exit 1
fi

# Clean up temporary files
echo -e "\nCleaning up temporary directory..."
rm -rf "${input_seqs_dir}"
echo "Deleted directory ${input_seqs_dir}"

echo -e "\n\033[0;32mNextflow pipeline process completed successfully.\033[0m"
echo -e "\033[0;32mNextflow results are in: ${nextflow_outdir}\033[0m\n"
