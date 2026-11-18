#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

usage() {
    echo "Usage: $0 [biomeme_data_path] [metadata_file]"
    echo ""
    echo "Run the Biomeme pipeline for ODIN data processing."
    echo ""
    echo "Arguments:"
    echo "  biomeme_data_path   Folder containing Biomeme qPCR results (Excel files)"
    echo "  metadata_file       Path to the metadata Excel file"
    echo ""
    echo "If arguments are not provided, you will be prompted interactively."
    exit 1
}

# Show usage if requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

# Load existing values if present
[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config biomeme_data_path
fallback_to_default_config metadata_file
fallback_to_default_config enlighten_data_path
# Add more variables here as needed for your pipeline

# Accept command line arguments
biomeme_data_path_arg="$1"
metadata_file_arg="$2"

echo -e "\033[0;33m[start_biomeme] biomeme_data_path: ${biomeme_data_path}\033[0m" >&2

# Prompt for biomeme_data_path and metadata_file using get_path
biomeme_data_path=$(get_path "Enter biomeme_data_path (Folder containing Biomeme qPCR results (Excel files))" "${biomeme_data_path}" "${biomeme_data_path_arg}" "directory")


# Extra check for biomeme_input_data subfolder
while [ ! -d "${biomeme_data_path}/biomeme_input_data" ]; do
    echo -e "\n\033[0;31mCould not find subfolder 'biomeme_input_data' in: ${biomeme_data_path}\033[0m"
    echo "Looking for: ${biomeme_data_path}/biomeme_input_data"
    biomeme_data_path=$(get_path "Please re-enter biomeme_data_path (must contain 'biomeme_input_data' subfolder)" "${biomeme_data_path}" "" "directory")
done

metadata_file=$(get_path "Enter path to metadata Excel file" "${metadata_file}" "${metadata_file_arg}" "file")

env_dir=$(dirname "${biomeme_data_path}")
script_dir=$(dirname "${SCRIPT_DIR}")

# Use config value if set, otherwise calculate default
[ -z "$enlighten_data_path" ] && enlighten_data_path="${script_dir}/enlighten/data"

# Update only biomeme_data_path, metadata_file, and enlighten_data_path in config file
set_config_value "${CONFIG_FILE}" biomeme_data_path "${biomeme_data_path}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" enlighten_data_path "${enlighten_data_path}"

# Change to the project root (parent of scripts)
cd "${SCRIPT_DIR}/.." || exit 1

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

# Prepare the python command
PY_CMD="python -m scripts.traverse_biomeme --data-root \"${biomeme_data_path}\" --env-root \"${env_dir}\" --enlighten-data-path \"${enlighten_data_path}\" --metadata-master \"${metadata_file}\""

# Echo the command before running
echo "Running command:"
echo "${PY_CMD}"

# Run the biomeme pipeline script
eval ${PY_CMD}
