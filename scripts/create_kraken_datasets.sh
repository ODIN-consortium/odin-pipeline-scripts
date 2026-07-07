#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

PY_SCRIPT="${SCRIPT_DIR}/create_kraken_datasets.py"

# Default paths (used only for internal fallback logic)
DEFAULT_KRAKEN_DIR="/mnt/c/Users/odin-/Documents/ODIN/data"
DEFAULT_METADATA_FILE="/mnt/c/Users/odin-/Documents/ODIN/data/metadata_test_environment.xlsx"
env_dir=$(dirname "${SCRIPT_DIR}")
DEFAULT_ENLIGHTEN_DATA_PATH="${env_dir}/enlighten/data"
DEFAULT_XLSX_DATA_PATH="/mnt/c/Users/odin-/Documents/ODIN/data/nanopore_processed"
DEFAULT_VENV_DIR="${HOME}/venv"

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS] [kraken2_path] [metadata_file] [pathogens_file] [output_path] [venv_folder]"
    echo ""
    echo "Create datasets from Kraken2 output files for visualization in Enlighten."
    echo ""
    echo "Options:"
    echo "  -h, --help      Display this help message and exit"
    echo "  --overwrite     Overwrite existing output files instead of merging with them"
    echo ""
    echo "Arguments:"
    echo "  kraken2_path        Directory containing kraken2 output files"
    echo "  metadata_file       Path to the metadata.xlsx file"
    echo "  pathogens_file      Path to the 'pathogens for database.xlsx' file"
    echo "  feather_output_path Directory where feather output files will be stored"
    echo "  xlsx_output_path    Directory where xlsx output files will be stored"
    echo "  venv_folder         Path to Python virtual environment (optional)"
    echo ""
    echo "If arguments are not provided, the script will prompt for them interactively."
    echo "Additional options for column names, file suffix, and split_by can be specified"
    echo "through interactive prompts during execution."
    exit 1
}

# Check for help option
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

# Extract --overwrite flag before positional arguments
overwrite_flag=""
for arg in "$@"; do
    if [ "$arg" = "--overwrite" ]; then
        overwrite_flag="--overwrite"
    fi
done
# Remove --overwrite from positional args so indices stay correct
args=()
for arg in "$@"; do
    [ "$arg" != "--overwrite" ] && args+=("$arg")
done
set -- "${args[@]}"

# Load config values if present
[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config kraken_dir
fallback_to_default_config output_dir
fallback_to_default_config metadata_file
fallback_to_default_config pathogens_file
fallback_to_default_config enlighten_data_path
fallback_to_default_config xlsx_data_path
fallback_to_default_config venv_folder

# Ensure config variables are set to a value (last resort: hardcoded default)
# For kraken_dir, fall back to output_dir first, then hardcoded default
[ -z "$kraken_dir" ] && kraken_dir="${output_dir:-$DEFAULT_KRAKEN_DIR}"
[ -z "$output_dir" ] && output_dir="$DEFAULT_KRAKEN_DIR"
[ -z "$metadata_file" ] && metadata_file="$DEFAULT_METADATA_FILE"
[ -z "$enlighten_data_path" ] && enlighten_data_path="$DEFAULT_ENLIGHTEN_DATA_PATH"
[ -z "$venv_folder" ] && venv_folder="$DEFAULT_VENV_DIR"

# Accept command line arguments
kraken2_path_arg="$1"
metadata_file_arg="$2"
pathogens_file_arg="$3"
enlighten_data_path_arg="$4"
xlsx_data_path_arg="$5"
venv_folder_arg="$6"

# Get paths with simplified prompts (always use config variable as default)
# Use kraken_dir from config as default for kraken2 input path
kraken2_path=$(get_path "Enter path to root of kraken2 files" "$kraken_dir" "$kraken2_path_arg" "directory") || exit $?
metadata_file=$(get_path "Enter path to metadata file" "$metadata_file" "$metadata_file_arg" "file") || exit $?

# Default pathogens file: config-loaded value takes priority, then the YAML in pipeline_scripts/config/
script_config_pathogens="$(realpath "${SCRIPT_DIR}/../config/pathogen_group_map.yaml" 2>/dev/null || echo "${SCRIPT_DIR}/../config/pathogen_group_map.yaml")"
default_pathogens_file="${pathogens_file:-$script_config_pathogens}"
pathogens_file=$(get_path "Enter path to pathogens file" "$default_pathogens_file" "$pathogens_file_arg" "file") || exit $?

enlighten_data_path=$(get_path "Enter Enlighten datasets output directory" "$enlighten_data_path" "$enlighten_data_path_arg" "none") || exit $?
mkdir -p "${enlighten_data_path}"

# Set xlsx_data_path default to $output_dir/nanopore_processed if still blank
# Use output_dir from config (not kraken2_path) for output location
default_xlsx_data_path="${output_dir}/nanopore_processed"
echo "[LOG] output_dir: $output_dir" >&2
echo "[LOG] xlsx_data_path before fallback: $xlsx_data_path" >&2
echo "[LOG] default_xlsx_data_path: $default_xlsx_data_path" >&2
[ -z "$xlsx_data_path" ] && xlsx_data_path="$default_xlsx_data_path"
echo "[LOG] xlsx_data_path after fallback: $xlsx_data_path" >&2

xlsx_data_path=$(get_path "Enter xlsx datasets output directory" "$xlsx_data_path" "$xlsx_data_path_arg" "none") || exit $?
echo "[LOG] xlsx_data_path after prompt: $xlsx_data_path" >&2
mkdir -p "${xlsx_data_path}"

# Set up virtual environment using shared function from config_utils.sh
venv_folder=$(setup_venv "$venv_folder_arg" "$venv_folder")

# Update config with values used
set_config_value "${CONFIG_FILE}" kraken_dir "${kraken2_path}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" pathogens_file "${pathogens_file}"
set_config_value "${CONFIG_FILE}" enlighten_data_path "${enlighten_data_path}"
set_config_value "${CONFIG_FILE}" xlsx_data_path "${xlsx_data_path}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

# Build the command
cmd="${PYTHON_CMD} \"${PY_SCRIPT}\" --data_path \"${kraken2_path}\" --metadata_file \"${metadata_file}\" --pathogens_file \"${pathogens_file}\" --feather_output_path \"${enlighten_data_path}\" --xlsx_output_path \"${xlsx_data_path}\" ${overwrite_flag}"

echo -e "\nRunning command:\n${cmd}\n"
run_python_script "${cmd}" || {
    echo -e "\n\033[0;31mFailed to create Kraken datasets. Check error messages above.\033[0m\n"
    exit 1
}

echo -e "\n\033[0;32mKraken datasets created successfully. Output is in: ${enlighten_data_path}\033[0m\n"
