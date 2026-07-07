#!/bin/bash
# scripts/parse_amr_json.sh
# Interactive launcher for parse_amr_json.py using shared config utilities.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source shared utilities (enforces sourcing safeguards inside)
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config_utils.sh"

# Determine config file precedence
if [ -f "${USER_CONFIG}" ]; then
    CONFIG_FILE="${USER_CONFIG}"
else
    CONFIG_FILE="${DEFAULT_CONFIG}"
fi

PY_SCRIPT="${SCRIPT_DIR}/parse_amr_json.py"

# Load existing config values if any
[ -f "${CONFIG_FILE}" ] && source "${CONFIG_FILE}"

# Fallbacks (will populate from DEFAULT_CONFIG if unset there)
fallback_to_default_config amr_data_path
fallback_to_default_config metadata_file
fallback_to_default_config amr_output_dir
fallback_to_default_config venv_folder

usage() {
    echo "Usage: $0 [-d DATA_PATH] [-o OUTPUT_DIR] [-x METADATA_FILE] [-v VENV_FOLDER]"
    echo ""
    echo "Interactive runner for parse_amr_json.py (AMR JSON aggregation)."
    echo ""
    echo "Options:"
    echo "  -d, --data-path       Root data path containing nanopore_processed/outputs_wf_metagenomics_amr"
    echo "  -o, --output-dir      Directory to store parsed AMR outputs"
    echo "  -x, --metadata-file   Metadata Excel file (required)"
    echo "  -v, --venv-folder     Python virtual environment (optional)"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "All options optional; will use config or prompt if missing."
    exit 0
}

data_path_arg=""
amr_output_dir_arg=""
metadata_file_arg=""
venv_folder_arg=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)          usage ;;
        -d|--data-path)     data_path_arg="$2";        shift 2 ;;
        -o|--output-dir)    amr_output_dir_arg="$2";   shift 2 ;;
        -x|--metadata-file) metadata_file_arg="$2";    shift 2 ;;
        -v|--venv-folder)   venv_folder_arg="$2";      shift 2 ;;
        *) echo "Unknown option: $1"; echo "Run with --help for usage."; exit 1 ;;
    esac
done

# Setup virtual environment (may prompt if not valid and not provided)
venv_folder="$(setup_venv "${venv_folder_arg}" "${venv_folder}")"

# Collect root data path
amr_data_path="$(get_path "Enter root data path (contains nanopore_processed/)" "${amr_data_path}" "${data_path_arg}" "directory")" || exit $?

# Collect output directory (where results will be written)
amr_output_dir="$(get_path "Enter output directory for AMR parsed data" "${amr_output_dir}" "${amr_output_dir_arg}" "none")" || exit $?
mkdir -p "${amr_output_dir}"
amr_output_dir="${amr_output_dir%/}"

# Metadata Excel (required now)
metadata_file="$(get_path "Enter metadata Excel file (required)" "${metadata_file}" "${metadata_file_arg}" "file")" || exit $?
if [ -z "${metadata_file}" ]; then
    echo -e "\033[0;31mError: metadata file is required.\033[0m"
    exit 1
fi
if [ ! -f "${metadata_file}" ]; then
    echo -e "\033[0;31mError: metadata file not found: ${metadata_file}\033[0m"
    exit 1
fi

# Persist settings
set_config_value "${CONFIG_FILE}" amr_data_path "${amr_data_path}"
set_config_value "${CONFIG_FILE}" amr_output_dir "${amr_output_dir}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"
set_config_value "${CONFIG_FILE}" venv_folder "${venv_folder}"

# Activate venv / determine python
activate_venv "${venv_folder}" || exit 1

# Build command using directory for --output (Python will create amr_data.* inside)
py_cmd="${PYTHON_CMD} \"${PY_SCRIPT}\" --data_path \"${amr_data_path}\" --metadata_excel \"${metadata_file}\" --output \"${amr_output_dir}\" --show-summary"

echo -e "\nRunning AMR parse command:\n${py_cmd}\n"

if ! run_python_script "${py_cmd}"; then
    echo -e "\n\033[0;31mError: AMR parsing failed.\033[0m"
    exit 1
fi

amr_data="${amr_output_dir}/amr_data.csv"
if [ ! -f "${amr_data}" ]; then
    echo -e "\033[0;31mError: Expected output CSV not found: ${amr_data}\033[0m"
    exit 1
fi

echo -e "\n\033[0;32mAMR parsing completed successfully.\033[0m"
echo -e "\033[0;32mOutput directory: ${amr_output_dir}\033[0m"
