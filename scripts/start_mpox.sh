#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

CONFIG_UTILS="${SCRIPT_DIR}/config_utils.sh"
CREATE_CSV_PY_SCRIPT="${SCRIPT_DIR}/create_mpox_samples_csv.py"

# Define pipeline_scripts folder (one level up from SCRIPT_DIR)
PIPELINE_SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default paths
DEFAULT_MINKNOW_DATA_DIR="/mnt/c/Users/odin-/Documents/mock_MinKNOW_output_folder/"
DEFAULT_OUTPUT_DIR="/mnt/c/Users/odin-/Documents/ODIN/data"
DEFAULT_CLADE="cladeii"
DEFAULT_SCHEME_VERSION="artic-inrb-mpox/2500/v1.0.0"
store_dir="${HOME}/store_dir"

usage() {
    echo "Usage: $0 [minknow_data_dir] [output_dir] [run_accession]"
    echo ""
    echo "Run artic-mpxv-nf Nextflow pipeline."
    echo ""
    echo "Arguments:"
    echo "  minknow_data_dir  Directory containing MinKNOW output folders"
    echo "  output_dir        Root directory of output data"
    echo "  run_accession     Run accession path (runName/sampleName/run_accession) within minknow_data_dir"
    exit 1
}

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

minknow_data_dir_arg="$1"
output_dir_arg="$2"
run_accession_arg="$3"

[ -f "${CONFIG_FILE}" ] && source <(grep '=' "${CONFIG_FILE}")

# Fallback: for each relevant variable, set from DEFAULT_CONFIG if blank/unset
fallback_to_default_config minknow_data_dir
fallback_to_default_config output_dir
fallback_to_default_config run_accession
fallback_to_default_config clade
fallback_to_default_config sample
fallback_to_default_config scheme_version
fallback_to_default_config metadata_file
fallback_to_default_config venv_folder
fallback_to_default_config store_dir

minknow_data_dir=$(get_path "Enter MinKNOW data directory" "${minknow_data_dir:-$DEFAULT_MINKNOW_DATA_DIR}" "${minknow_data_dir_arg}" "directory") || exit $?

# Get run accession using the common function
if ! get_run_accession "${minknow_data_dir}" "${run_accession_arg}"; then
    exit 1
fi

run_accession="${RUN_ACCESSION}"
runaccession_dir="${RUNACCESSION_DIR}"

fastq_dir="${runaccession_dir}/fastq_pass"

output_dir=$(get_path "Enter path to root output data directory" "${output_dir:-$DEFAULT_OUTPUT_DIR}" "${output_dir_arg}" "none") || exit $?
mkdir -p "${output_dir}"

# Get metadata file
metadata_file=$(get_path "Enter metadata file" "${metadata_file:-$DEFAULT_METADATA_FILE}" "${metadata_file_arg}" "file") || exit $?

echo -e "\n"
# Prompt for clade
clade=$(ask_choice "cladei" "cladeia" "cladeib" "cladeii" "cladeiia" "cladeiib" --default "${DEFAULT_CLADE}" --prompt "Select clade")
echo -e "Selected clade: $clade\n"

# Prompt for scheme version
scheme_version=$(ask_choice "artic-inrb-mpox/2500/v1.0.0" "artic-inrb-mpox/400/v1.0.0" "yale-mpox/2000/v1.0.0-cladei" "yale-mpox/2000/v1.0.0-cladeii" "bccdc-mpox/2500/v2.3.0" --default "${DEFAULT_SCHEME_VERSION}" --prompt "Select scheme version")
echo -e "Selected: $scheme_version\n"

# Note: run_accession, clade, and sample are session-specific, not saved to config
set_config_value "${CONFIG_FILE}" minknow_data_dir "${minknow_data_dir}"
set_config_value "${CONFIG_FILE}" output_dir "${output_dir}"
set_config_value "${CONFIG_FILE}" scheme_version "${scheme_version}"
set_config_value "${CONFIG_FILE}" metadata_file "${metadata_file}"

# Set up output directory for wf-artic-mpxv-nf
output_dir_clean="${output_dir%/}"
nextflow_outdir=$(build_nextflow_outdir "${output_dir_clean}" "${run_accession}" "nanopore_processed" "outputs_wf_artic-mpxv-nf")

# Prepare the output directory (ensures it exists and is empty)
if ! prepare_output_directory "${nextflow_outdir}" "Nextflow output directory"; then
    exit 1
fi

# Activate venv and get Python command
activate_venv "${venv_folder}" || exit 1

# Create samples CSV file
output_csv_file="${output_dir_clean}/nanopore_processed/mpox_samples_${run_accession}.csv"
echo -e "\nCreating samples CSV file..."
run_python_script "${PYTHON_CMD} \"${CREATE_CSV_PY_SCRIPT}\" \"${run_accession}\" \"${fastq_dir}\" \"${output_csv_file}\" \"${metadata_file}\"" || {
    echo -e "\n\033[0;31mError: Failed to run the Python script for ${fastq_dir}.\033[0m"
    exit 1
}

if [ ! -f "${output_csv_file}" ]; then
    echo -e "\n\033[0;31mError: CSV file was not created at ${output_csv_file}.\033[0m"
    exit 1
fi

echo -e "\nUsing store_dir: ${store_dir}"

nextflow_cmd="nextflow run artic-network/artic-mpxv-nf -c \"${PIPELINE_SCRIPTS_DIR}/config/odin.config\" -profile epi2me --fastq \"${fastq_dir}\" --sample_sheet \"${output_csv_file}\" --clade \"${clade}\" --store_dir \"${store_dir}\" --scheme_version \"${scheme_version}\" --out_dir \"${nextflow_outdir}\""
echo -e "\nRunning Nextflow command:\n"
echo "${nextflow_cmd}"
echo

if ! eval ${nextflow_cmd}; then
    echo -e "\n\033[0;31mError: Failed to run the Nextflow pipeline.\033[0m"
    exit 1
fi

echo -e "\n\033[0;32mNextflow pipeline process completed successfully.\033[0m"
echo -e "\033[0;32mNextflow results are in: ${nextflow_outdir}\033[0m\n"

echo -e "Activating the conda environment for squirrel..."
eval "$(${HOME}/miniforge3/bin/conda shell.bash hook)"
conda activate squirrel

# Prepend wrappers so both `iqtree` and `iqtree3` calls from squirrel's snakemake
# go through our scripts, which inject --seqtype DNA (required for IQ-TREE 3 when
# most sequences consist of ambiguous bases, as is normal for low-coverage mpox).
export PATH="${PIPELINE_SCRIPTS_DIR}/wrappers:${PATH}"

squirrel_output_dir=$(build_nextflow_outdir "${output_dir_clean}" "${run_accession}" "nanopore_processed" "output_squirrel")
mkdir -p "${squirrel_output_dir}"

echo -e "Running squirrel phylogenetic analysis..."
squirrel_cmd="squirrel \"${nextflow_outdir}/all_consensus.fasta\" --run-apobec3-phylo --include-background --clade \"${clade}\" --outdir \"${squirrel_output_dir}\""
echo "${squirrel_cmd}"
echo

if ! eval ${squirrel_cmd}; then
    echo -e "\n\033[0;31mError: Failed to run the squirrel pipeline.\033[0m"
    exit 1
fi

conda deactivate
conda deactivate
