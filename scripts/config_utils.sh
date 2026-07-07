# Prevent execution — allow only sourcing
(return 0 2>/dev/null) || {
  echo "This script must be sourced, not executed." >&2
  exit 1
}

# Centralized config path variables
if [ -z "${SCRIPT_DIR}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo -e "\033[0;33m[config_utils] SCRIPT_DIR was not defined in the calling script. Using: ${SCRIPT_DIR}\033[0m" >&2
else
    echo -e "\033[0;32m[config_utils] SCRIPT_DIR is set to: ${SCRIPT_DIR}\033[0m" >&2
fi

if [ -z "${USER_CONFIG}" ]; then
    USER_CONFIG="${HOME}/.odin_ml/odin_paths.txt"
    echo -e "\033[0;33m[config_utils] USER_CONFIG not set, using default: ${USER_CONFIG}\033[0m" >&2
else
    echo -e "\033[0;32m[config_utils] USER_CONFIG is set to: ${USER_CONFIG}\033[0m" >&2
fi
if [ -z "${DEFAULT_CONFIG}" ]; then
    DEFAULT_CONFIG="${SCRIPT_DIR}/odin_paths.txt"
    echo -e "\033[0;33m[config_utils] DEFAULT_CONFIG not set, using default: ${DEFAULT_CONFIG}\033[0m" >&2
else
    echo -e "\033[0;32m[config_utils] DEFAULT_CONFIG is set to: ${DEFAULT_CONFIG}\033[0m" >&2
fi
if [ -z "${OLD_CONFIG}" ]; then
    OLD_CONFIG="${SCRIPT_DIR}/nanopore_paths.txt"
    echo -e "\033[0;33m[config_utils] OLD_CONFIG not set, using default: ${OLD_CONFIG}\033[0m" >&2
else
    echo -e "\033[0;32m[config_utils] OLD_CONFIG is set to: ${OLD_CONFIG}\033[0m" >&2
fi

# Function that combines Windows path conversion and relative path resolution
# Arguments:
#   $1: Base directory for relative paths
#   $2: Path to resolve
# Returns:
#   Fully resolved path
resolve_path() {
    local base_dir="$1"
    shift
    local input_dir="$*"  # capture everything else as the path

    # Strip leading and trailing double quotes
    input_dir="${input_dir%\"}"
    input_dir="${input_dir#\"}"

    # Convert backslashes to forward slashes
    input_dir="${input_dir//\\//}"

    # Strip leading \\wsl.localhost/<DISTRO>/ if present
    if [[ "$input_dir" =~ ^//wsl\.localhost/([^/]+)/(.+) ]]; then
        input_dir="/${BASH_REMATCH[2]}"
    fi

    # Collapse multiple forward slashes into one
    while [[ "$input_dir" == *"//"* ]]; do
        input_dir="${input_dir//\/\//\/}"
    done

    # Handle Windows drive letters like C:/path or C:path
    if [[ "$input_dir" =~ ^([A-Za-z]):/?(.*) ]]; then
        local drive_letter="${BASH_REMATCH[1],,}" # lowercase
        local rest="${BASH_REMATCH[2]}"
        rest="${rest#/}"  # remove leading slash if present
        input_dir="/mnt/$drive_letter/$rest"
    fi

    # If still relative, resolve relative to base_dir
    if [[ ! "$input_dir" = /* ]]; then
        input_dir="$base_dir/$input_dir"
    fi

    # Normalize path
    input_dir="$(realpath -m "$input_dir")"

    echo "$input_dir"
}

# Function to check if a virtual environment exists and can be activated
# Arguments:
#   $1: Path to the virtual environment directory
# Returns:
#   0 if the venv exists and can be activated, 1 otherwise
is_valid_venv() {
    local venv_path="$1"

    # Check if the directory exists
    if [ ! -d "${venv_path}" ]; then
        return 1
    fi

    # Check if activation script exists
    local activate_script=""
    if [ -f "${venv_path}/bin/activate" ]; then
        activate_script="${venv_path}/bin/activate"
    elif [ -f "${venv_path}/Scripts/activate" ]; then
        activate_script="${venv_path}/Scripts/activate"
    else
        return 1
    fi

    # Try to activate the venv in a subshell
    (
        source "${activate_script}" 2>/dev/null || exit 1
        command -v python >/dev/null 2>&1 || exit 1
    ) >/dev/null 2>&1

    return $?
}

# Function to handle virtual environment setup
# Arguments:
#   $1: The virtual environment path provided as an argument
#   $2: The default virtual environment path
# Returns:
#   The path to the virtual environment to use, or an empty string if using base environment
setup_venv() {
    local venv_arg="$1"
    local default_venv="$2"

    if [ -n "${venv_arg}" ] && is_valid_venv "${venv_arg}"; then
        echo -e "\033[0;32m\nUsing provided virtual environment at: ${venv_arg}\033[0m" >&2
        echo "${venv_arg}"
        return 0
    elif is_valid_venv "${default_venv}"; then
        echo -e "\033[0;32m\nUsing default virtual environment at: ${default_venv}\033[0m" >&2
        echo "${default_venv}"
        return 0
    else
        local venv=$(get_path "Enter path to Python virtual environment (leave empty to use base environment)" "" "${venv_arg}" "none")
        if [ -z "${venv}" ]; then
            echo -e "\033[0;33mUsing base environment (no venv)\033[0m" >&2
            echo ""
        elif ! is_valid_venv "${venv}"; then
            echo -e "\033[0;33mWarning: ${venv} is not a valid virtual environment. Using base environment.\033[0m" >&2
            echo ""
        else
            echo -e "\033[0;32mUsing virtual environment at: ${venv}\033[0m" >&2
            echo "${venv}"
        fi
        return 0
    fi
}


# Function to prompt for a path with validation
# Arguments:
#   $1: Prompt text
#   $2: Default value
#   $3: Value from argument (optional)
#   $4: Validation type ('directory', 'file', or 'none')
get_path() {
    local prompt_text="$1"
    local default_value="$2"
    local arg_value="$3"
    local validation_type="$4"
    local result_value

    # If argument provided, validate and use it or exit
    if [ -n "${arg_value}" ]; then
        # Resolve and convert path
        arg_value=$(resolve_path "${SCRIPT_DIR}" "${arg_value}")

        if [ "${validation_type}" = "directory" ] && [ ! -d "${arg_value}" ]; then
            echo -e "\033[0;31mError: Directory not found: ${arg_value}\033[0m" >&2
            exit 1
        elif [ "${validation_type}" = "file" ] && [ ! -f "${arg_value}" ]; then
            echo -e "\033[0;31mError: File not found: ${arg_value}\033[0m" >&2
            exit 1
        fi
        # Argument is valid, return it
        echo "${arg_value}"
        return
    fi

    # No argument provided, use default value initially
    result_value=$(resolve_path "${SCRIPT_DIR}" "${default_value}")

    # Prompt user for input
    read -r -p "${prompt_text} [${result_value}]: " user_input
    if [ -n "${user_input}" ]; then
        # Resolve and convert user input path
        result_value=$(resolve_path "${SCRIPT_DIR}" "${user_input}")
    fi

    # Validate user input
    while [ "${validation_type}" = "directory" -a ! -d "${result_value}" ] || \
          [ "${validation_type}" = "file" -a ! -f "${result_value}" ]; do

        echo -e "\033[0;31m${validation_type^} not found: ${result_value}\033[0m" >&2
        read -r -p "${prompt_text} [$(resolve_path "${SCRIPT_DIR}" "${default_value}")]: " user_input

        result_value=$(resolve_path "${SCRIPT_DIR}" "${user_input:-$default_value}")
    done

    echo "${result_value}"
}

# Function to update a single value in a config file without removing others
# Usage: set_config_value CONFIG_FILE KEY VALUE
set_config_value() {
    local config_file="$1"
    local key="$2"
    local value="$3"
    local tmpfile
    tmpfile=$(mktemp)

    if [ -f "${config_file}" ] && grep -q "^${key}=" "${config_file}"; then
        # Update existing key
        sed "s|^${key}=.*|${key}=\"${value//\"/\\\"}\"|" "${config_file}" > "${tmpfile}"
        mv "${tmpfile}" "${config_file}"
    else
        # If the file doesn't exist or the key isn't in it
        if [ -f "${config_file}" ]; then
            # Add the key-value pair
            echo "${key}=\"${value//\"/\\\"}\"" >> "${config_file}"
        else
            # Create new file with the key-value pair
            echo "${key}=\"${value//\"/\\\"}\"" > "${config_file}"
        fi
    fi
}

# Function to activate Python virtual environment and determine Python command
# Returns the Python command to use in PYTHON_CMD variable
activate_venv() {
    local venv_folder="$1"

    # Activate venv if specified and exists
    if [ -n "${venv_folder}" ]; then
        if [ -d "${venv_folder}" ]; then
            if [ -f "${venv_folder}/bin/activate" ]; then
                # Unix-like
                # shellcheck disable=SC1090
                source "${venv_folder}/bin/activate"
                # Force output to stderr to ensure display
                echo -e "\033[0;32mActivated Python virtual environment at: ${venv_folder}\033[0m" >&2
            elif [ -f "${venv_folder}/Scripts/activate" ]; then
                # Windows
                # shellcheck disable=SC1090
                source "${venv_folder}/Scripts/activate"
                # Force output to stderr to ensure display
                echo -e "\033[0;32mActivated Python virtual environment at: ${venv_folder}\033[0m" >&2
            else
                echo -e "\n\033[0;31mNo activate script found in venv folder: ${venv_folder}\033[0m\n" >&2
                return 1
            fi
        else
            echo -e "\n\033[0;31mvenv folder not found: ${venv_folder}\033[0m\n" >&2
            return 1
        fi
    else
        echo -e "\033[0;33mNo venv folder specified. Using base environment.\033[0m" >&2
    fi

    # Determine which Python to use
    if command -v python3 &>/dev/null; then
        PYTHON_CMD=python3
    elif command -v python &>/dev/null; then
        PYTHON_CMD=python
    else
        echo "Python is not installed." >&2
        return 1
    fi

    # Export PYTHON_CMD so it's available to the calling script
    export PYTHON_CMD
    return 0
}



select_run_accession() {
    local root_dir="$1"
    local __resultvar="$2"

    # Find fastq_pass directories first
    local temp_file=$(mktemp)

    find "${root_dir}" -type d -name "fastq_pass" | while read -r fastq_dir; do
        # Check for barcode directories
        if find "${fastq_dir}" -maxdepth 1 -type d -name "barcode*" -print -quit | grep -q .; then
            # See if any barcode dir has at least one fastq.gz file
            for barcode_dir in "${fastq_dir}"/barcode*; do
                if [ -d "${barcode_dir}" ] && find "${barcode_dir}" -type f -name "*.fastq.gz" -print -quit | grep -q .; then
                    # Found at least one fastq.gz file in this barcode dir
                    local run_accession_dir=$(dirname "${fastq_dir}")
                    local rel_path="${run_accession_dir#${root_dir}/}"
                    echo "${rel_path}" >> "${temp_file}"
                    # Break after finding first valid barcode dir for this fastq_pass
                    break
                fi
            done
        fi
    done

    # Read unique paths into an array
    mapfile -t options < <(sort -u "${temp_file}")
    rm "${temp_file}"

    if [ "${#options[@]}" -eq 0 ]; then
        echo "No valid run accession directories found in ${root_dir}" >&2
        return 1
    fi

    echo "Select a runAccession:"
    for i in "${!options[@]}"; do
        printf "[%d] %s\n" $((i + 1)) "${options[$i]}"
    done

    while true; do
        read -rp "Enter the number of your choice: " choice
        if [[ "${choice}" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
            local selected="${options[$((choice - 1))]}"
            if [[ "${__resultvar}" ]]; then
                printf -v "${__resultvar}" '%s' "${selected}"
            fi
            return 0
        else
            echo "Invalid selection. Please enter a number between 1 and ${#options[@]}."
        fi
    done
}

# Function to build the Nextflow output directory path
# Intelligently constructs the path by checking if parts are already included
# Arguments:
#   $1: Base output directory
#   $2: Run accession base
#   $3+: Expected path components (e.g. "nanopore_processed" "outputs_taxprofiler")
build_nextflow_outdir() {
    local output_dir="$1"
    local run_accession_base="$2"
    shift 2  # Remove the first two arguments

    # Remove trailing slash if present
    output_dir="${output_dir%/}"

    # Set expected components - either from arguments or default
    local expected_components=()
    if [ $# -eq 0 ]; then
        expected_components=("nanopore_processed" "outputs_taxprofiler" "${run_accession_base}")
    else
        # Add all provided components plus the run_accession at the end
        for component in "$@"; do
            expected_components+=("${component}")
        done
        expected_components+=("${run_accession_base}")
    fi

    local result="${output_dir}"

    # Check if each component is already in the path
    for component in "${expected_components[@]}"; do
        # If this component is already the end of the path, don't add it again
        if [[ "${result##*/}" != "${component}" ]]; then
            # Check if the component is anywhere in the path
            if [[ "${result}" != *"/${component}/"* ]] && [[ "${result}" != *"/${component}" ]]; then
                result="${result}/${component}"
            fi
        fi
    done

    echo "${result}"
}

# Run a Python script and color only error messages in red
run_python_script() {
    local cmd="$1"

    # Run the command with a pipe to process the output
    eval "${cmd}" 2>&1 | while IFS= read -r line; do
        if [[ "${line}" == ERROR:* ]]; then
            # Display error messages in red
            echo -e "\n\033[0;31m${line}\033[0m"
        else
            # Display normal output as is
            echo "${line}"
        fi
    done

    # Capture the exit code of the Python command, not the pipe
    return ${PIPESTATUS[0]}
}

# Verify the run accession directory structure
verify_run_structure() {
    local run_dir="$1"
    local fastq_dir="${run_dir}/fastq_pass"

    if [ ! -d "${fastq_dir}" ]; then
        echo -e "\n\033[0;31mError: fastq_pass directory not found in ${run_dir}\033[0m"
        return 1
    fi

    local barcode_count=$(find "${fastq_dir}" -type d -name "barcode*" | wc -l)
    if [ "${barcode_count}" -eq 0 ]; then
        echo -e "\n\033[0;31mError: No barcode* directories found in ${fastq_dir}\033[0m"
        return 1
    fi

    local fastq_count=$(find "${fastq_dir}" -name "*.fastq.gz" | wc -l)
    if [ "${fastq_count}" -eq 0 ]; then
        echo -e "\n\033[0;31mError: No *.fastq.gz files found in barcode directories under ${fastq_dir}\033[0m"
        return 1
    fi

    return 0
}

# Function to process fastq files
process_fastq_files() {
    local fastq_pass_dir="$1"
    local input_seqs_dir="$2"
    local run_accession="$3"

    # Ensure the directory is empty/exists
    if [ -d "${input_seqs_dir}" ]; then
        echo -e "\nCleaning up input sequences directory: ${input_seqs_dir}"
        rm -rf "${input_seqs_dir}"/*
    else
        echo -e "\nCreating input sequences directory: ${input_seqs_dir}"
        mkdir -p "${input_seqs_dir}"
    fi

    # Concatenate fastq.gz files for each barcode directory
    echo -e "\nConcatenating fastq.gz files for each barcode directory..."
    for barcode_dir in $(find "${fastq_pass_dir}" -type d -name "barcode*"); do
    # Check if directory exists and is readable
        if [ -r "${barcode_dir}" ]; then
            barcode=$(basename "${barcode_dir}" 2>/dev/null) || {
                echo "Error accessing: ${barcode_dir}" >&2
                continue
            }
        else
            echo "Cannot access directory: ${barcode_dir}" >&2
            continue
        fi
        echo "Found barcode directory: ${barcode_dir}"
        output_fastq="${input_seqs_dir}/${barcode}_${run_accession}.fastq.gz"

        echo "Processing ${barcode}..."
        fastq_count=$(find "${barcode_dir}" -name "*.fastq.gz" | wc -l)
        fastq_count=${fastq_count:-0}
        if [ "${fastq_count}" -eq 0 ]; then
            echo "  No fastq.gz files found in ${barcode_dir}, skipping"
            continue
        fi

        # Concatenate all fastq.gz files into one
        cat "${barcode_dir}"/*.fastq.gz > "${output_fastq}"
        echo "  Created: ${output_fastq}"
    done
}

# Function to get run accession with standardized logic
# Arguments:
#   $1: MinKNOW data directory
#   $2: Run accession argument (optional)
# Sets the following environment variables:
#   RUN_ACCESSION: The base run accession name
#   RUNACCESSION_DIR: Full path to the run accession directory
# Returns:
#   0 on success, 1 on failure
get_run_accession() {
    local minknow_data_dir="$1"
    local run_accession_arg="$2"
    local run_accession=""
    local runaccession_dir=""

    if [ -n "${run_accession_arg}" ]; then
        run_accession="${run_accession_arg}"
    else
        echo -e "\nSelecting run accession path from ${minknow_data_dir}"
        run_accession=""
        select_run_accession "${minknow_data_dir}" run_accession
        if [ $? -ne 0 ] || [ -z "${run_accession}" ]; then
            echo -e "\n\033[0;31mNo valid run accession selected. Exiting.\033[0m"
            return 1
        fi
        echo "Selected run accession path: ${run_accession}"
    fi

    # Build full path to run accession directory
    if [[ "${run_accession}" == "${minknow_data_dir}"* ]]; then
        runaccession_dir="${run_accession}"
    else
        runaccession_dir="${minknow_data_dir}/${run_accession}"
    fi

    # Extract run_accession from the LAST part of the path
    IFS='/' read -r -a path_parts <<< "${run_accession}"
    run_accession="${path_parts[${#path_parts[@]}-1]}"

    echo -e "\nUsing run accession: ${run_accession}"
    echo -e "Full run accession path: ${runaccession_dir}\n"

    # Verify run directory structure
    if ! verify_run_structure "${runaccession_dir}"; then
        return 1
    fi

    # Export environment variables for the calling script to use
    export RUN_ACCESSION="${run_accession}"
    export RUNACCESSION_DIR="${runaccession_dir}"

    return 0
}

# Function to prepare an output directory
# Checks if the directory exists, if it's empty, and creates it if needed
# Arguments:
#   $1: Path to the output directory to prepare
#   $2: Optional message to display with the directory (default: "Output directory")
#   $3: Optional mode flag — pass "force" to remove an existing non-empty directory,
#       or "skip" to exit 0 (success) if it already exists and is not empty.
# Returns:
#   0 if success or skipped, 1 if directory exists and is not empty or couldn't be created
#   Return code 2 signals "skipped" — caller should exit 0 without doing further work.
prepare_output_directory() {
    local dir_path="$1"
    local dir_description="${2:-Output directory}"
    local force_flag="${3:-}"

    echo -e "\n${dir_description}: ${dir_path}"

    # Check if directory exists and is not empty
    if [ -d "${dir_path}" ] && [ "$(ls -A "${dir_path}" 2>/dev/null)" ]; then
        if [[ "${force_flag}" == "force" ]]; then
            echo -e "\n\033[0;33mWarning: ${dir_description} already exists and is not empty — removing (--force).\033[0m"
            rm -rf "${dir_path}" || {
                echo -e "\n\033[0;31mError: Failed to remove existing ${dir_description}: ${dir_path}\033[0m"
                return 1
            }
        elif [[ "${force_flag}" == "skip" ]]; then
            echo -e "\n\033[0;33mSkipping: ${dir_description} already exists and is not empty — skipping (--skip-existing).\033[0m"
            return 2
        else
            echo -e "\n\033[0;31mError: ${dir_description} already exists and is not empty.\033[0m"
            echo -e "\033[0;31mPlease remove or rename the existing directory before continuing.\033[0m\n"
            return 1
        fi
    fi

    # Create directory if it doesn't exist
    mkdir -p "${dir_path}" || {
        echo -e "\n\033[0;31mError: Failed to create ${dir_description}: ${dir_path}\033[0m"
        return 1
    }

    return 0
}

# Function: ask_choice
# Usage:
#   choice=$(ask_choice --prompt "Select clade" \
#                       --default "cladeii" \
#                       "cladei" "cladeia" "cladeib" "cladeii" "cladeiia" "cladeiib")
ask_choice() {
    local prompt="Please choose an option:"
    local default=""
    local options=()
    local base_dir="$PWD"   # default base directory for relative paths

    # Parse args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prompt)
                prompt="$2"
                shift 2
                ;;
            --default)
                default="$2"
                shift 2
                ;;
            --base-dir)
                base_dir="$2"
                shift 2
                ;;
            *)
                options+=("$1")
                shift
                ;;
        esac
    done

    options+=("Other (custom)")

    # Print menu once
    printf "%s\n" "$prompt" >&2
    for i in "${!options[@]}"; do
        local num=$((i+1))
        if [[ "${options[i]}" == "$default" ]]; then
            printf "[%d] %s [default]\n" "$num" "${options[i]}" >&2
        else
            printf "[%d] %s\n" "$num" "${options[i]}" >&2
        fi
    done

    # Loop to handle user input
    while true; do
        printf "Enter the number of your choice: " >&2
        read -r REPLY   # <- use -r to keep backslashes intact

        if [[ -z "$REPLY" && -n "$default" ]]; then
            echo "$default"
            return 0
        elif [[ "$REPLY" =~ ^[0-9]+$ ]] && (( REPLY >= 1 && REPLY <= ${#options[@]} )); then
            local opt="${options[REPLY-1]}"
            if [[ "$opt" == "Other (custom)" ]]; then
                while true; do
                    read -r -p "Enter your custom value: " custom_value
                    if [[ -n "$custom_value" ]]; then
                        # If input looks like a path, resolve it
                        if [[ "$custom_value" == *[\\/*]* ]]; then
                            custom_value=$(resolve_path "$base_dir" "$custom_value")
                        fi
                        echo "$custom_value"
                        return 0
                    else
                        echo "Custom value cannot be empty. Please try again." >&2
                    fi
                done
            else
                echo "$opt"
                return 0
            fi
        else
            echo "Invalid selection. Please enter a number between 1 and ${#options[@]}." >&2
        fi
    done
}

# Migrate old config to user config if needed; seed from default on first run
migrate_old_config_if_needed() {
    mkdir -p "$(dirname "$USER_CONFIG")"
    if [ ! -f "$USER_CONFIG" ]; then
        if [ -f "$OLD_CONFIG" ]; then
            cp "$OLD_CONFIG" "$USER_CONFIG"
        elif [ -f "$DEFAULT_CONFIG" ]; then
            cp "$DEFAULT_CONFIG" "$USER_CONFIG"
            echo -e "\033[0;32m[config_utils] Created user config at: ${USER_CONFIG}\033[0m" >&2
        fi
    fi
}

# Fallback: set variable from DEFAULT_CONFIG if blank/unset in current environment
# Usage: fallback_to_default_config VAR_NAME
fallback_to_default_config() {
    local var_name="$1"
    local current_value="${!var_name}"
    if [ -z "$current_value" ] && [ -f "$DEFAULT_CONFIG" ]; then
        local default_value
        default_value=$(grep "^${var_name}=" "$DEFAULT_CONFIG" | cut -d'=' -f2-)
        if [ -n "$default_value" ]; then
            export "$var_name"="$default_value"
        fi
    fi
}

migrate_old_config_if_needed
