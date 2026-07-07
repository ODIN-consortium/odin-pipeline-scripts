#!/bin/bash

# Source the utility script as early as possible to set centralized config variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

PY_SCRIPT="${SCRIPT_DIR}/concatenate_fastq_by_sample.py"

# Define pipeline_scripts folder (one level up from SCRIPT_DIR)
PIPELINE_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load existing values if present
[ -f "${CONFIG_FILE}" ] && source "${CONFIG_FILE}"

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config output_dir
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS] [minknow_data_dir] [output_dir] [sample_id] [metadata_file] [tmp_dir] [venv_folder]"
    echo ""
    echo "Concatenate FASTQ files from multiple run_accessions that share the same sample_id."
    echo ""
    echo "Options:"
    echo "  -h, --help      Display this help message and exit"
    echo ""
    echo "Arguments:"
    echo "  minknow_data_dir  Directory containing MinKNOW output folders"
    echo "  output_dir        Root directory of output data where files will be stored"
    echo "  sample_id         Sample ID to find matching run_accessions"
    echo "  metadata_file     Path to the metadata.xlsx file"
    echo "  tmp_dir          Temporary directory for concatenated files"
    echo "  venv_folder      Path to Python virtual environment folder (leave empty to use base environment)"
    echo ""
    echo "The script will:"
    echo "  1. Identify all run_accessions with the same sample_id"
    echo "  2. Concatenate fastq.gz files by barcode across all matching run_accessions"
    echo "  3. Output one file per barcode in tmp_dir as: barcode_{sample_id}.fastq.gz"
    echo ""
    echo "If arguments are not provided, the script will prompt for them interactively."
    exit 1
}

# Check for help option
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    usage
fi

# Accept command line arguments
minknow_data_dir_arg="$1"
output_dir_arg="$2"
sample_id_arg="$3"
metadata_file_arg="$4"
tmp_dir_arg="$5"
venv_folder_arg="$6"

# Set up virtual environment using shared function from config_utils.sh
venv_folder=$(setup_venv "${venv_folder_arg}" "${venv_folder}")

# Get MinKNOW data directory
minknow_data_dir=$(get_path "Enter MinKNOW data directory" "${minknow_data_dir}" "${minknow_data_dir_arg}" "directory") || exit $?

# Get output directory (for compatibility with the Python script signature)
output_dir=$(get_path "Enter path to root output data directory" "${output_dir}" "${output_dir_arg}" "none") || exit $?
mkdir -p "${output_dir}"
output_dir_clean="${output_dir%/}"

# Get sample ID
if [ -n "${sample_id_arg}" ]; then
    sample_id="${sample_id_arg}"
else
  read -r -p "Enter sample_id [${sample_id}]: " user_input
  sample_id="${user_input:-$sample_id}"
  if [ -z "${sample_id}" ]; then
      echo "Error: sample_id cannot be empty."
      exit 1
  fi
fi

# Get metadata file
metadata_file=$(get_path "Enter metadata file" "${metadata_file}" "${metadata_file_arg}" "file") || exit $?

# Get tmp directory for concatenated files
if [ -n "${tmp_dir_arg}" ]; then
    tmp_dir=$(resolve_path "${SCRIPT_DIR}" "${tmp_dir_arg}")
else
    # Default tmp_dir to a subdirectory of output_dir
    default_tmp_dir="${output_dir_clean}/concatenated_fastq"
    tmp_dir=$(get_path "Enter directory for concatenated fastq files" "${default_tmp_dir}" "" "none") || exit $?
fi
mkdir -p "${tmp_dir}"
echo "Using temporary directory for concatenated files: ${tmp_dir}"

# Save values to config file
set_config_value "${CONFIG_FILE}" minknow_data_dir "${minknow_data_dir}"
set_config_value "${CONFIG_FILE}" output_dir "${output_dir}"
set_config_value "${CONFIG_FILE}" sample_id "${sample_id}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

echo -e "\n\033[0;36m==========================================\033[0m"
echo -e "\033[0;36mConcatenating FASTQ files for sample: ${sample_id}\033[0m"
echo -e "\033[0;36m==========================================\033[0m"
echo "MinKNOW data directory: ${minknow_data_dir}"
echo "Output directory: ${output_dir}"
echo "Sample ID: ${sample_id}"
echo "Metadata file: ${metadata_file}"
echo "Temporary directory: ${tmp_dir}"
echo "Python environment: ${venv_folder:-base environment}"
echo -e "\033[0;36m==========================================\033[0m\n"

# Run the Python script
py_cmd="${PYTHON_CMD} \"${PY_SCRIPT}\" --minknow_data_dir \"${minknow_data_dir}\" --output_dir \"${output_dir}\" --sample_id \"${sample_id}\" --metadata_file \"${metadata_file}\" --tmp_dir \"${tmp_dir}\""

echo "Running concatenation script..."
run_python_script "${py_cmd}" || {
    echo -e "\n\033[0;31mError: Failed to concatenate FASTQ files for sample ${sample_id}.\033[0m"
    exit 1
}

echo -e "\n\033[0;32m==========================================\033[0m"
echo -e "\033[0;32mConcatenation completed successfully!\033[0m"
echo -e "\033[0;32m==========================================\033[0m"
echo "Concatenated files are available in: ${tmp_dir}"
echo -e "\033[0;32m==========================================\033[0m\n"
