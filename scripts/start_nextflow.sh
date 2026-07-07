#!/bin/bash

# Source the utility script as early as possible to set centralized config variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi


PY_SCRIPT="${SCRIPT_DIR}/create_all_samples_csv.py"
METADATA_SCRIPT="${SCRIPT_DIR}/get_run_metadata.py"
VERIFY_PY_SCRIPT="${SCRIPT_DIR}/verify_nanopore_metadata.py"
KRAKEN_DATASETS_PY_SCRIPT="${SCRIPT_DIR}/create_kraken_datasets.py"
CONCATENATE_FASTQ_SCRIPT="${SCRIPT_DIR}/concatenate_fastq_by_sample.py"

# Define pipeline_scripts folder (one level up from SCRIPT_DIR)
PIPELINE_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load existing values if present
[ -f "${CONFIG_FILE}" ] && source "${CONFIG_FILE}"

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config output_dir
fallback_to_default_config run_accession
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder
fallback_to_default_config databases_file
fallback_to_default_config enlighten_data_path
fallback_to_default_config xlsx_data_path

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS] [minknow_data_dir] [output_dir] [run_accession] [metadata_file] [venv_folder] [databases_file]"
    echo ""
    echo "Process Nanopore sequencing data through the nf-core/taxprofiler pipeline."
    echo ""
    echo "Options:"
    echo "  -h, --help              Display this help message and exit"
    echo "  --auto-merge            Automatically merge all related run_accessions without prompting"
    echo "  --profile NAME          Nextflow profile to use (default: odin; e.g. odin_big)"
    echo "  --save-reads            Save Kraken2 classified/unclassified reads (--kraken2_save_reads --kraken2_save_readclassifications)"
    echo "  --mpox-clade CLADE      After pipeline completes, extract Mpox reads and run alignment for given clade"
    echo "                          (implies --save-reads; e.g. cladeia, cladeib, cladeii)"
    echo ""
    echo "Arguments:"
    echo "  minknow_data_dir  Directory containing MinKNOW output folders"
    echo "  output_dir        Root directory of output data where files will be stored"
    echo "  run_accession     Run accession path (runName/sampleName/run_accession) within minknow_data_dir"
    echo "  metadata_file     Path to the metadata.xlsx file"
    echo "  databases_file    Path to databases.csv file (default: ${databases_file})"
    echo "  venv_folder       Path to Python virtual environment folder (leave empty to use base environment)"
    echo ""
    echo "If arguments are not provided, the script will prompt for them interactively."
    echo "For run_accession, if not provided, a selection menu will be displayed."
    exit 1
}

# Parse flags, collecting positional args separately
AUTO_MERGE=false
FORCE=false
SKIP_EXISTING=false
NF_PROFILE="odin"
SAVE_READS=false
MPOX_CLADE=""
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)       usage ;;
        --auto-merge)    AUTO_MERGE=true; shift ;;
        --force)         FORCE=true; shift ;;
        --skip-existing) SKIP_EXISTING=true; shift ;;
        --profile)       NF_PROFILE="$2"; shift 2 ;;
        --save-reads)    SAVE_READS=true; shift ;;
        --mpox-clade)    MPOX_CLADE="$2"; SAVE_READS=true; shift 2 ;;
        *)               POSITIONAL_ARGS+=("$1"); shift ;;
    esac
done
set -- "${POSITIONAL_ARGS[@]}"

# Accept command line arguments
minknow_data_dir_arg="$1"
output_dir_arg="$2"
run_accession_arg="$3"
metadata_file_arg="$4"
databases_file_arg="$5"
venv_folder_arg="$6"



# Set taxprofiler path from config or use default, and strip trailing slashes
taxprofiler_path="${taxprofiler_dir}"
taxprofiler_path="${taxprofiler_path%/}"

# Set up virtual environment using shared function from config_utils.sh
venv_folder=$(setup_venv "${venv_folder_arg}" "${venv_folder}")

# Get MinKNOW data directory
minknow_data_dir=$(get_path "Enter MinKNOW data directory" "${minknow_data_dir}" "${minknow_data_dir_arg}" "directory") || exit $?

# Get run accession using the common function
if ! get_run_accession "${minknow_data_dir}" "${run_accession_arg}"; then
    exit 1
fi

# Now use the exported environment variables
run_accession="${RUN_ACCESSION}"
runaccession_dir="${RUNACCESSION_DIR}"

# Get output directory
output_dir=$(get_path "Enter path to root output data directory" "${output_dir}" "${output_dir_arg}" "none") || exit $?
mkdir -p "${output_dir}"
output_dir_clean="${output_dir%/}"

# Get databases file
databases_file=$(get_path "Enter databases file" "${databases_file}" "${databases_file_arg}" "file") || exit $?

# Get metadata file
metadata_file=$(get_path "Enter metadata file" "${metadata_file}" "${metadata_file_arg}" "file") || exit $?

# Setup paths for visualization
metadata_dir=$(dirname "${metadata_file}")
pathogens_file="${SCRIPT_DIR}/../config/pathogen_group_map.yaml"

# Always derive these from output_dir so they stay in sync when output_dir changes
enlighten_data_path="${output_dir_clean}/enlighten"
xlsx_data_path="${output_dir_clean}/nanopore_processed"

# Save values to config file
# Note: run_accession is session-specific, not saved to config
set_config_value "${CONFIG_FILE}" minknow_data_dir "${minknow_data_dir}"
set_config_value "${CONFIG_FILE}" output_dir "${output_dir}"
set_config_value "${CONFIG_FILE}" databases_file "${databases_file}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" pathogens_file "${pathogens_file}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"
set_config_value "${CONFIG_FILE}" enlighten_data_path "${enlighten_data_path}"
set_config_value "${CONFIG_FILE}" xlsx_data_path "${xlsx_data_path}"

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

# Update the nextflow output directory to use the file identifier instead of run_accession
nextflow_outdir=$(build_nextflow_outdir "${output_dir_clean}" "${file_identifier}" "nanopore_processed" "outputs_taxprofiler")

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

# Create samples CSV file using the file identifier
output_csv_file="${output_dir_clean}/nanopore_processed/all_samples_${file_identifier}.csv"
echo -e "\nCreating samples CSV file..."
run_python_script "${PYTHON_CMD} \"${PY_SCRIPT}\" --run_accession \"${run_accession}\" --input_seqs_directory \"${input_seqs_dir}\" --output_csv_file \"${output_csv_file}\" --metadata_file \"${metadata_file}\"" || {
    echo -e "\n\033[0;31mError: Failed to run the Python script for ${input_seqs_dir}.\033[0m"
    exit 1
}

if [ ! -f "${output_csv_file}" ]; then
    echo -e "\n\033[0;31mError: CSV file was not created at ${output_csv_file}.\033[0m"
    exit 1
fi

# Run the Nextflow pipeline
SAVE_READS_FLAGS=""
$SAVE_READS && SAVE_READS_FLAGS="--kraken2_save_reads --kraken2_save_readclassifications"
nextflow_cmd="nextflow run -ansi-log false -with-trace \"${nextflow_outdir}/trace.txt\" -with-report \"${nextflow_outdir}/report.html\" ${taxprofiler_path}/taxprofiler -profile ${NF_PROFILE} --input \"${output_csv_file}\" --databases \"${databases_file}\" --outdir \"${nextflow_outdir}\" -c \"$HOME/pipeline_scripts/config/odin.config\" --run_kraken2 ${SAVE_READS_FLAGS} --run_krona"
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

# Create visualization datasets
echo -e "\nCreating Enlighten datasets for visualization..."
kraken_cmd="${PYTHON_CMD} \"${KRAKEN_DATASETS_PY_SCRIPT}\" --data_path \"${output_dir}\" --metadata_file \"${metadata_file}\" --pathogens_file \"${pathogens_file}\" --feather_output_path \"${enlighten_data_path}\" --xlsx_output_path \"${xlsx_data_path}\""
run_python_script "${kraken_cmd}" || {
    echo -e "\n\033[0;31mFailed to create Enlighten datasets. Check error messages above.\033[0m\n"
    exit 1
}
echo -e "\n\033[0;32mEnlighten datasets created successfully. Output is in: ${enlighten_data_path}\033[0m\n"

# Extract Mpox reads from each Kraken2 database output folder if requested.
# Iterates over report files per barcode and pre-filters by taxid, so alignment
# only runs on barcodes that actually have signal — not every barcode in the run.
if [[ -n "${MPOX_CLADE}" ]]; then
    echo -e "\nExtracting Mpox reads (clade: ${MPOX_CLADE})..."

    # Derive the taxid for the requested clade so we can pre-filter by Kraken2 report.
    case "${MPOX_CLADE,,}" in
        cladei|cladeia|mpox_cladei|mpox_cladeia|cladeib|mpox_cladeib|cladeii|mpox_cladeii)
            _filter_taxid="10244" ;;
        *) _filter_taxid="" ;;
    esac

    kraken2_dir="${nextflow_outdir}/kraken2"
    if [[ -d "${kraken2_dir}" ]]; then
        for db_dir in "${kraken2_dir}"/*/; do
            [[ -d "${db_dir}" ]] || continue
            for _report in "${db_dir}"*report.txt; do
                [ -f "${_report}" ] || continue
                # Skip barcodes where the taxid is absent from the Kraken2 report
                if [[ -n "${_filter_taxid}" ]] && ! grep -qw "${_filter_taxid}" "${_report}"; then
                    continue
                fi
                _barcode=$(basename "${_report}" | cut -d_ -f1)
                echo -e "  Processing: ${_barcode} in ${db_dir}${_filter_taxid:+ (taxid ${_filter_taxid} detected)}"
                "${SCRIPT_DIR}/extract_reads.sh" "${db_dir}" "" "${MPOX_CLADE}" "" "${_barcode}" || \
                    echo -e "  \033[0;33mWarning: Mpox extraction failed for ${_barcode} in ${db_dir} — continuing.\033[0m"
            done
        done
    else
        echo -e "\033[0;33mWarning: Kraken2 output directory not found at ${kraken2_dir} — skipping Mpox extraction.\033[0m"
    fi
fi

# Call the start_enlighten.sh script with the enlighten_data_path
#"${SCRIPT_DIR}/start_enlighten.sh" "${enlighten_data_path}"