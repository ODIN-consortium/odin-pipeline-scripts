#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

# Accept command line argument
enlighten_data_path_arg="$1"
root_dir=$(dirname "${SCRIPT_DIR}")
docker_compose_file="${root_dir}/enlighten/docker-compose.yml"
docker_compose_dir=$(dirname "${docker_compose_file}")
# Load existing values if present
[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")
[ -f "${CONFIG_FILE}" ] && source "${CONFIG_FILE}"

# Fallback: set from DEFAULT_CONFIG if blank/unset
enlighten_data_path_arg="$1"
fallback_to_default_config enlighten_data_path

# Use argument if provided, otherwise use value from config, otherwise use default
env_dir=$(dirname "${SCRIPT_DIR}")
if [ -n "${enlighten_data_path_arg}" ]; then
    enlighten_data_path="${enlighten_data_path_arg}"
    # Only update config file if user explicitly provided a new path
    set_config_value "${CONFIG_FILE}" enlighten_data_path "${enlighten_data_path}"
elif [ -z "${enlighten_data_path}" ]; then
    # No value in config and no argument, use default
    enlighten_data_path="${env_dir}/enlighten/data"
fi
echo -e "Using Enlighten data path: ${enlighten_data_path}\n"

# Resolve the data path
enlighten_data_path=$(resolve_path "${SCRIPT_DIR}" "${enlighten_data_path}")

# Resolve the public files path
enlighten_public_files_path=$(resolve_path "${SCRIPT_DIR}" "${root_dir}/enlighten/files/public")

echo -e "\nSetting up Enlighten visualization..."

if [ ! -f "${docker_compose_file}" ]; then
    echo -e "\n\033[0;33mWarning: Could not find docker-compose.yml file at ${docker_compose_file}.\033[0m"
    echo -e "\033[0;33mEnlighten visualization will not be started.\033[0m\n"
    exit 1
fi

echo "Found docker-compose.yml at ${docker_compose_file}"

# Export environment variables for Docker Compose to use
export HOST_DATA_PATH="${enlighten_data_path}"
export HOST_PUBLIC_FILES_PATH="${enlighten_public_files_path}"

echo "Setting HOST_DATA_PATH=${HOST_DATA_PATH}"
echo "Setting HOST_PUBLIC_FILES_PATH=${HOST_PUBLIC_FILES_PATH}"

# Verify paths exist
if [ ! -d "${HOST_DATA_PATH}" ]; then
    echo -e "\n\033[0;31mError: Data path does not exist: ${HOST_DATA_PATH}\033[0m"
    exit 1
fi

if [ ! -d "${HOST_PUBLIC_FILES_PATH}" ]; then
    echo -e "\n\033[0;33mWarning: Public files path does not exist: ${HOST_PUBLIC_FILES_PATH}\033[0m"
    echo -e "Creating directory...\033[0m"
    mkdir -p "${HOST_PUBLIC_FILES_PATH}"
fi

# Start or restart the container
cd "${docker_compose_dir}" || exit 1
if docker compose ps 2>/dev/null | grep -q "Up"; then
    echo "Restarting Enlighten container..."
    docker compose down
    docker compose up -d
else
    echo "Starting Enlighten container..."
    docker compose up -d
fi

echo -e "\n\033[0;32mEnlighten visualization is now available at http://localhost\033[0m\n"
