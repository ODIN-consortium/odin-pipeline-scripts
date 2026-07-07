#!/bin/bash
# Integrity checking utility for ODIN pipeline
#
# IMPORTANT: Run this script directly (./integrity_check.sh), not by sourcing it.
# For unified logging, do NOT run integrity_check.py directly; always use this shell script.
#
# This script will call integrity_check.py ONCE. If you see duplicate output, check for accidental multiple invocations.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/integrity_check.py"

source "${SCRIPT_DIR}/config_utils.sh"
migrate_old_config_if_needed

# Load user config if present, otherwise default
if [ -f "$USER_CONFIG" ]; then
    source <(grep '=' "$USER_CONFIG")
else
    source <(grep '=' "$DEFAULT_CONFIG")
fi

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config databases_file
fallback_to_default_config venv_folder
fallback_to_default_config output_dir
fallback_to_default_config metadata_file
fallback_to_default_config enlighten_data_path
fallback_to_default_config taxprofiler_dir
fallback_to_default_config biomeme_data_path
fallback_to_default_config xlsx_data_path

# Log and construct xlsx_data_path as in create_kraken_datasets.sh
log_prefix="[LOG integrity_check.sh]"
echo "$log_prefix output_dir: $output_dir" >&2
echo "$log_prefix xlsx_data_path before fallback: $xlsx_data_path" >&2
default_xlsx_data_path="${output_dir}/nanopore_processed"
echo "$log_prefix default_xlsx_data_path: $default_xlsx_data_path" >&2
[ -z "$xlsx_data_path" ] && xlsx_data_path="$default_xlsx_data_path"
echo "$log_prefix xlsx_data_path after fallback: $xlsx_data_path" >&2

# If pathogens_file is not set, construct it from metadata_file
if [ -z "$pathogens_file" ] && [ -n "$metadata_file" ]; then
    pathogens_file="$(dirname "$SCRIPT_DIR")/config/pathogen_group_map.yaml"
fi

# Export all variables needed by the Python script
export minknow_data_dir
export databases_file
export venv_folder
export output_dir
export metadata_file
export enlighten_data_path
export taxprofiler_dir
export biomeme_data_path
export pathogens_file
export xlsx_data_path

# Determine venv directory (must be set before exporting ODIN_VENV_PATH)
VENV_DIR="${venv_folder:-$DEFAULT_VENV_DIR}"

# Export venv and project root for Python hints (after VENV_DIR is set)
export ODIN_VENV_PATH="$VENV_DIR"
export ODIN_PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments for verbose flag
VERBOSE=""
for arg in "$@"; do
    if [ "$arg" == "--verbose" ]; then
        VERBOSE="--verbose"
    fi
    # You can add more flags here if needed
    # e.g. if [ "$arg" == "--dry-run" ]; then ...
    # etc.
done


# ANSI color codes for banners
BOLD='\033[1m'
OKBLUE='\033[94m'
OKCYAN='\033[96m'
OKGREEN='\033[92m'
WARNING='\033[93m'
FAIL='\033[91m'
ENDC='\033[0m'

# Save original stdout/stderr
exec 3>&1 4>&2
# Redirect all shell output to log file and terminal
exec > >(tee "$SCRIPT_DIR/integrity_check.log") 2>&1

# VIRTUAL ENVIRONMENT CHECK BANNER
printf "\n${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"
printf "${BOLD}${OKBLUE}%s${ENDC}\n" "VIRTUAL ENVIRONMENT CHECK"
printf "${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"

if [ -d "$VENV_DIR" ]; then
    printf "  ${OKCYAN}Checking for Python virtual environment...${ENDC}\n"
    printf "  ${OKGREEN}[OK]${ENDC} Virtual environment found at: ${BOLD}%s${ENDC}\n" "$VENV_DIR"
    printf "  ${OKCYAN}Activating virtual environment and running integrity check...${ENDC}\n"
    . "$VENV_DIR/bin/activate"
    # Remove DEBUG output: do not log which python and version
    printf "${OKCYAN}VIRTUAL ENVIRONMENT CHECK complete.${ENDC}\n"

    # NEXTFLOW CHECK BANNER
    printf "\n${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"
    printf "${BOLD}${OKBLUE}%s${ENDC}\n" "NEXTFLOW INSTALLATION CHECK"
    printf "${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"
    if command -v nextflow >/dev/null 2>&1; then
        printf "  ${OKGREEN}[OK]${ENDC} Nextflow is installed: $(command -v nextflow)\n"
        nextflow_version=$(nextflow -version 2>&1 | grep -m1 'version' | awk '{print $2}')
        printf "  ${OKCYAN}Nextflow version: %s${ENDC}\n" "$nextflow_version"

        # Check latest Nextflow version from GitHub (with timeout and error handling)
        printf "  ${OKCYAN}Checking for latest Nextflow version online...${ENDC}\n"
        latest_version=""
        github_json=$(curl -s --max-time 5 https://api.github.com/repos/nextflow-io/nextflow/releases/latest)
        if [ $? -eq 0 ] && [ -n "$github_json" ]; then
            latest_version=$(echo "$github_json" | grep '"tag_name"' | sed -E 's/.*"v?([0-9.]+)".*/\1/')
            if [ -n "$latest_version" ]; then
                printf "  ${OKCYAN}Latest Nextflow version: %s${ENDC}\n" "$latest_version"
                if [ "$nextflow_version" != "$latest_version" ]; then
                    printf "  ${WARNING}[UPGRADE AVAILABLE]${ENDC} Your Nextflow version is out of date.\n"
                    printf "\n${WARNING}To upgrade Nextflow, run the following command:${ENDC}\n"
                    printf "${WARNING}nextflow self-update${ENDC}\n\n"
                    printf "${WARNING}See https://www.nextflow.io/docs/latest/getstarted.html#installation for details.${ENDC}\n\n"
                else
                    printf "  ${OKGREEN}[OK]${ENDC} You are running the latest Nextflow version.\n"
                fi
            else
                printf "  ${WARNING}[WARNING]${ENDC} Could not parse latest Nextflow version from GitHub.\n"
            fi
        else
            printf "  ${WARNING}[WARNING]${ENDC} Could not check latest Nextflow version (no internet or GitHub unavailable).\n"
            printf "  ${WARNING}If you want to upgrade Nextflow, run:${ENDC}\n"
            printf "${WARNING}nextflow self-update${ENDC}\n\n"
            printf "${WARNING}See https://www.nextflow.io/docs/latest/getstarted.html#installation for details.${ENDC}\n\n"
        fi
    else
        printf "  ${FAIL}[NOT FOUND]${ENDC} Nextflow is not installed or not in your PATH.\n"
        printf "  ${FAIL}Please install Nextflow as described in:${ENDC}\n"
        printf "    ${BOLD}${OKBLUE}%s${ENDC}\n" "../doc/setup_mobile_lab_computer.md (see 'Installing Nextflow')"
        printf "  ${FAIL}Aborting integrity check.${ENDC}\n"
        deactivate
        exit 1
    fi
else
    printf "  ${WARNING}[NOT FOUND]${ENDC} Virtual environment not found at: ${BOLD}%s${ENDC}\n" "$VENV_DIR"
    printf "  ${FAIL}[SKIP]${ENDC} Skipping Python integrity check.\n"
    printf "${OKCYAN}VIRTUAL ENVIRONMENT CHECK complete.${ENDC}\n"
fi

# LINUX DISTRIBUTION AND VERSION CHECK
if [ -f /etc/os-release ]; then
    DISTRO_NAME=$(grep '^ID=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    DISTRO_VERSION=$(grep '^VERSION_ID=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    DISTRO_PRETTY=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    if [ "$DISTRO_NAME" = "ubuntu" ] && ([[ "$DISTRO_VERSION" == 22.04* ]] || [[ "$DISTRO_VERSION" == 24.04* ]]); then
        printf "  ${OKGREEN}\n[OK]${ENDC} Detected Linux distribution: ${BOLD}%s${ENDC}\n" "$DISTRO_PRETTY"
    else
        printf "  ${WARNING}[WARNING]${ENDC} Detected Linux distribution: ${BOLD}%s${ENDC}\n" "$DISTRO_PRETTY"
        printf "  ${WARNING}This setup requires Ubuntu 22.04 or 24.04 as per the documentation.\n"
        printf "  Please install and use Ubuntu 22.04 or 24.04 for full compatibility.${ENDC}\n"
    fi
else
    printf "  ${WARNING}[WARNING]${ENDC} Could not detect Linux distribution (missing /etc/os-release).\n"
fi

# ENLIGHTEN DOCKER IMAGE CHECK
printf "\n${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"
printf "${BOLD}${OKBLUE}%s${ENDC}\n" "ENLIGHTEN DOCKER IMAGE CHECK"
printf "${BOLD}${OKBLUE}%s${ENDC}\n" "------------------------------------------------------------"
ENL_IMAGE="norceresearch1/basic-enlweb:odin1.0.3"
printf "  ${OKCYAN}Required Docker image: %s${ENDC}\n" "$ENL_IMAGE"

# Check if Docker is available and running
if ! command -v docker >/dev/null 2>&1; then
    printf "  ${WARNING}[WARNING]${ENDC} Docker is not installed or not in your PATH.\n"
    printf "  ${WARNING}\nPlease install Docker and ensure it is available in your shell.\n"
    printf "  ${WARNING}\nSee https://docs.docker.com/get-docker/ for installation instructions.${ENDC}\n"
    printf "  ${WARNING}For mobile lab setup, see: pdf-doc/setup_mobile_lab_computer.pdf${ENDC}\n\n"
elif ! docker info >/dev/null 2>&1; then
    printf "  ${WARNING}[WARNING]${ENDC} Docker is installed but not running or not contactable.\n"
    printf "  ${WARNING}\nPlease ensure Docker Desktop (or your Docker daemon) is running and accessible.\n"
    printf "  ${WARNING}\nSee https://docs.docker.com/go/wsl2/ for WSL 2 integration help if using WSL.${ENDC}\n"
    printf "  ${WARNING}For mobile lab setup, see: pdf-doc/setup_mobile_lab_computer.pdf${ENDC}\n\n"
else
    if ! docker image inspect "$ENL_IMAGE" >/dev/null 2>&1; then
        printf "  ${WARNING}[NOT FOUND]${ENDC} Docker image not found locally: ${BOLD}%s${ENDC}\n" "$ENL_IMAGE"
        printf "\n${WARNING}To pull the required image, run the following command:${ENDC}\n"
        printf "${WARNING}\ndocker pull %s${ENDC}\n\n" "$ENL_IMAGE"
        printf "${WARNING}See https://hub.docker.com/r/norceresearch1/basic-enlweb for details.${ENDC}\n\n"
    else
        printf "  ${OKGREEN}[OK]${ENDC} Docker image is available locally: ${BOLD}%s${ENDC}\n" "$ENL_IMAGE"
    fi
fi

# Now call Python at the very end, after all banners and checks
exec 1>&3 2>&4
python "$PY_SCRIPT" $VERBOSE
exec > >(tee -a "$SCRIPT_DIR/integrity_check.log") 2>&1
