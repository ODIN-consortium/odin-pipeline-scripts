#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

PY_SCRIPT="${SCRIPT_DIR}/verify_nanopore_metadata.py"

# Default paths
DEFAULT_MINKNOW_DATA_DIR="/mnt/c/Users/odin-/Documents/mock_MinKNOW_output_folder/"
DEFAULT_METADATA_FILE="/mnt/c/Users/odin-/Documents/ODIN/data/metadata_test_environment.xlsx"
DEFAULT_VENV_DIR="${HOME}/venv"


# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS] [minknow_data_dir] [metadata_file] [venv_folder] [run_accession]"
    echo ""
    echo "Verify that the expected directory structure and files exist for Nanopore sequencing data,"
    echo "based on metadata in an Excel file."
    echo ""
    echo "Options:"
    echo "  -h, --help      Display this help message and exit"
    echo ""
    echo "Arguments:"
    echo "  minknow_data_dir  Directory containing MinKNOW output folders"
    echo "  metadata_file     Path to the metadata.xlsx file"
    echo "  venv_folder       Path to Python virtual environment (optional)"
    echo "  run_accession     Specific run accession to verify (optional)"
    echo ""
    echo "If arguments are not provided, the script will prompt for them interactively."
    echo "If run_accession is provided, only that specific run will be verified."
    echo "Otherwise, all runs in the metadata file will be verified."
    exit 1
}

# Check for help option
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

# Accept arguments
minknow_data_dir_arg="$1"
metadata_file_arg="$2"
venv_folder_arg="$3"
run_accession_arg="$4"

# Get paths and setup environment
[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder

metadata_file=$(get_path "Enter full path to metadata.xlsx file" "${metadata_file:-$DEFAULT_METADATA_FILE}" "${metadata_file_arg}" "file") || exit $?

# Set up virtual environment using shared function from config_utils.sh
venv_folder=$(setup_venv "${venv_folder_arg}" "${DEFAULT_VENV_DIR}")

# Save to config file
set_config_value "${CONFIG_FILE}" minknow_data_dir "${minknow_data_dir}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

# Build and execute the Python command
py_cmd="${PYTHON_CMD} \"${PY_SCRIPT}\" \"${minknow_data_dir}\" \"${metadata_file}\""
if [ -n "${run_accession_arg}" ]; then
    py_cmd="${py_cmd} \"${run_accession_arg}\""
fi

run_python_script "${py_cmd}" || {
    echo -e "\n\033[0;31mVerification of metadata file ${metadata_file} failed. \033[0m\n"
    exit 1
}
