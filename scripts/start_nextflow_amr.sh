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
AMR_KRAKEN2_DB_SCRIPT="${SCRIPT_DIR}/amr_kraken2_db.py"

# Define pipeline_scripts folder (one level up from SCRIPT_DIR)
PIPELINE_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default paths
DEFAULT_MINKNOW_DATA_DIR="${HOME}/ODIN/minknow_output/"
DEFAULT_OUTPUT_DIR="${HOME}/ODIN/data"
DEFAULT_DATABASE_SET="PlusPF-8"
DEFAULT_AMR_DB="card"
# wf-metagenomics release. The workflow's tools (abricate, fastcat, Kraken 2 wrappers) change
# between releases and with them the results, so a run without a revision is not reproducible.
WF_METAGENOMICS_REVISION="${WF_METAGENOMICS_REVISION:-v2.14.2}"
DEFAULT_METADATA_FILE="${HOME}/ODIN/data/metadata.xlsx"

# Parse flags, collecting positional args separately
AUTO_MERGE=false
FORCE=false
SKIP_EXISTING=false
DATABASE_ARG=""
AMR_REPLICATES_ARG=""
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            echo "Usage: $0 [--auto-merge] [--force] [--skip-existing] [--database PATH|download] [--amr-replicates pool|per_barcode] [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder]"
            echo ""
            echo "  --database PATH   Local Kraken2 database directory for the classification step (it needs a"
            echo "                    Bracken database*mers.kmer_distrib file). 'download' uses the downloaded"
            echo "                    database_set. Without it: kraken2_db_amr from the config file, else the"
            echo "                    kraken2 database of databases.csv when its directory has a Bracken file,"
            echo "                    else the downloaded database_set."
            echo "  --amr-replicates pool|per_barcode"
            echo "                    What to do with the barcodes numbered as replicates of one sample (the"
            echo "                    'replicate' column of the nanopore sheet): pool them into one input before"
            echo "                    screening (default, as odin_pipeline does) or screen each barcode. Also the"
            echo "                    amr_replicates config setting. Give the same value to parse_amr_json.sh."
            exit 0 ;;
        --auto-merge)        AUTO_MERGE=true; shift ;;
        --force)             FORCE=true; shift ;;
        --skip-existing)     SKIP_EXISTING=true; shift ;;
        --database)          DATABASE_ARG="$2"; shift 2 ;;
        --amr-replicates)    AMR_REPLICATES_ARG="$2"; shift 2 ;;
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
fallback_to_default_config kraken2_db_amr
fallback_to_default_config databases_file
fallback_to_default_config amr_replicates
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder

# Replicate barcodes: pooled into one input (as odin_pipeline's default) or screened per barcode
amr_replicates="${AMR_REPLICATES_ARG:-${amr_replicates:-pool}}"
case "${amr_replicates}" in
    pool)        POOL_FLAG="" ;;
    per_barcode) POOL_FLAG="--no-pool-replicates" ;;
    *) echo "Error: --amr-replicates must be 'pool' or 'per_barcode', got '${amr_replicates}'." >&2; exit 1 ;;
esac

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

# Local Kraken2 database and taxonomy for the classification step: checked now, so that a bad
# path stops the run before the FASTQ files are concatenated.
amr_db_setting="${DATABASE_ARG:-${kraken2_db_amr:-}}"
amr_db_lines=$(${PYTHON_CMD} "${AMR_KRAKEN2_DB_SCRIPT}" --setting "${amr_db_setting}" --databases-csv "${databases_file:-}") || {
    echo -e "\n\033[0;31mAMR Kraken2 database check failed. Exiting.\033[0m\n"
    exit 1
}
kraken2_db_path=$(sed -n 1p <<< "${amr_db_lines}")
kraken2_taxonomy_path=$(sed -n 2p <<< "${amr_db_lines}")
if [[ -n "${kraken2_db_path}" ]]; then
    echo "Kraken2 database for the AMR run: ${kraken2_db_path}"
    [[ -n "${kraken2_taxonomy_path}" ]] && echo "Taxonomy: ${kraken2_taxonomy_path}"
else
    echo "Kraken2 database for the AMR run: downloaded database_set"
fi

# Create temporary directory for input sequences
# Use $TMPDIR if set (to avoid filling tmpfs), otherwise fall back to /tmp
input_seqs_dir="$(mktemp -d "${TMPDIR:-/tmp}/input_seqs_${run_accession}_XXXXXX")"

# Resolve the file identifier from metadata (lightweight — no file I/O)
MERGE_FLAG=""
$AUTO_MERGE && MERGE_FLAG="--auto-merge"
resolve_cmd="${PYTHON_CMD} \"${CONCATENATE_FASTQ_SCRIPT}\" --minknow_data_dir \"${minknow_data_dir}\" --output_dir \"${output_dir_clean}\" --run_accession \"${run_accession}\" --metadata_file \"${metadata_file}\" --tmp_dir \"${input_seqs_dir}\" ${MERGE_FLAG} ${POOL_FLAG} --resolve-identifier"
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
concatenate_cmd="${PYTHON_CMD} \"${CONCATENATE_FASTQ_SCRIPT}\" --minknow_data_dir \"${minknow_data_dir}\" --output_dir \"${output_dir_clean}\" --run_accession \"${run_accession}\" --metadata_file \"${metadata_file}\" --tmp_dir \"${input_seqs_dir}\" ${MERGE_FLAG} ${POOL_FLAG}"
run_python_script "${concatenate_cmd}" || {
    echo -e "\n\033[0;31mError: Failed to concatenate fastq files for run_accession ${run_accession}.\033[0m"
    rm -rf "${input_seqs_dir}"
    exit 1
}

# Nextflow arguments - use the temporary directory with barcode structure
fastq_dir="${input_seqs_dir}"
database_set="${database_set:-${DEFAULT_DATABASE_SET}}"
amr_db="${amr_db:-${DEFAULT_AMR_DB}}"

# Build nextflow command. --database_set is still required with --database (wf-metagenomics
# validates it); the taxonomy is the database's own taxonomy/ folder when it has one, else
# wf-metagenomics supplies one.
nextflow_cmd="nextflow run -ansi-log false -with-trace \"${nextflow_outdir}/trace.txt\" -with-report \"${nextflow_outdir}/report.html\" -c \"${PIPELINE_SCRIPTS_DIR}/config/odin.config\" -profile epi2me epi2me-labs/wf-metagenomics -r ${WF_METAGENOMICS_REVISION} --fastq \"${fastq_dir}\" --database_set \"${database_set}\""
[[ -n "${kraken2_db_path}" ]] && nextflow_cmd+=" --database \"${kraken2_db_path}\""
[[ -n "${kraken2_taxonomy_path}" ]] && nextflow_cmd+=" --taxonomy \"${kraken2_taxonomy_path}\""
nextflow_cmd+=" --amr --amr_db \"${amr_db}\" --out_dir \"${nextflow_outdir}\""
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
