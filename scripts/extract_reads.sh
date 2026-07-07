#!/bin/bash
# Extract pathogen reads from a taxprofiler kraken2_save_reads output,
# align them against a reference genome, and produce a confidence summary.
#
# Steps:
#   1. Align all Kraken2-classified reads against the target reference (minimap2)
#   2. Extract reads that mapped to the reference
#   3. Compute coverage statistics (samtools)
#   4. Look up sample metadata from the ODIN metadata workbook
#   5. Write a plain-text confidence summary report
#
# Known taxon shortcuts  (pass as taxon_label; ref_accession is then optional)
# ─────────────────────────────────────────────────────────────────────────────
#  taxon_label        NCBI taxid  Reference accession   Description
#  ─────────────────  ──────────  ────────────────────  ─────────────────────────────
#  mpox_cladeia       10244       NC_003310.1           Mpox Clade Ia (Central African)
#  mpox_cladeib       10244       PP899475.1            Mpox Clade Ib (Kamituga / 2024 DRC) *
#  mpox_cladeii       10244       NC_063383.1           Mpox Clade II (2022 outbreak)
# ─────────────────────────────────────────────────────────────────────────────
#  * PP899475.1 is the default Clade Ib reference — override with explicit ref_accession if needed.
#  For any other taxon, provide ref_accession explicitly.
#
# Usage:
#   ./extract_reads.sh [kraken2_outdir] [output_dir] [taxon_label] [ref_accession]
#
# Arguments:
#   kraken2_outdir  Path to the kraken2/db*/ directory (contains .classified.fastq.gz + .report.txt)
#   output_dir      Directory to write all outputs (FASTQ, BAM, summary report)
#   taxon_label     Label for output files and report (e.g. mpox_cladeii, salmonella_enterica)
#   ref_accession   NCBI accession of reference genome (e.g. NC_063383.1)
#                   Optional if taxon_label is a known shortcut (see table above)
#
# Examples:
#   # Mpox Clade II (shortcut — no accession needed)
#   ./extract_reads.sh /path/to/kraken2/db2 "" cladeii
#
#   # Any pathogen with explicit accession
#   ./extract_reads.sh /path/to/kraken2/db2 "" salmonella_enterica NC_003197.2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config_utils.sh"

if [ -f "$USER_CONFIG" ]; then
    CONFIG_FILE="$USER_CONFIG"
else
    CONFIG_FILE="$DEFAULT_CONFIG"
fi

# Reference cache directory
store_dir="${HOME}/store_dir"
REF_CACHE_DIR="${store_dir}/pathogen_refs"

# Auto-detect NORCE corporate CA certificate for SSL operations
_NORCE_CA=""
for _ca_candidate in \
    "/mnt/c/ProgramData/NORCE/cer/NORCE_CA.cer" \
    "/etc/ssl/certs/NORCE_CA.pem" \
    "${CURL_CA_BUNDLE:-}"
do
    if [ -f "${_ca_candidate}" ]; then
        _NORCE_CA="${_ca_candidate}"
        break
    fi
done

usage() {
    echo "Usage: $0 [kraken2_outdir] [output_dir] [taxon_label] [ref_accession]"
    echo ""
    echo "Align Kraken2-classified reads to a reference genome and report coverage."
    echo ""
    echo "Known taxon shortcuts (ref_accession optional for these):"
    echo "  mpox_cladeia  → NC_003310.1  (Mpox Clade Ia, Central African, NCBI taxid 10244)"
    echo "  mpox_cladeib  → PP899475.1   (Mpox Clade Ib, Kamituga/2024 DRC, NCBI taxid 10244)"
    echo "  mpox_cladeii  → NC_063383.1  (Mpox Clade II, 2022 outbreak,    NCBI taxid 10244)"
    echo ""
    echo "Arguments:"
    echo "  kraken2_outdir  Path to the kraken2/db*/ output directory"
    echo "  output_dir      Directory to write outputs (FASTQ, BAM, report)"
    echo "  taxon_label     Label for output files (e.g. mpox_cladeii, salmonella_enterica)"
    echo "  ref_accession   NCBI accession of reference genome"
    echo "  barcode         Barcode prefix to process (e.g. barcode16); required when the"
    echo "                  directory contains files for multiple barcodes"
    echo ""
    echo "Requirements:"
    echo "  minimap2, samtools (apt/conda)"
    exit 1
}

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

kraken2_outdir_arg="$1"
output_dir_arg="$2"
taxon_arg="$3"
ref_arg="$4"
barcode_filter="$5"   # optional: barcode prefix to select a specific sample (e.g. "barcode16")

[ -f "${CONFIG_FILE}" ] && source "${CONFIG_FILE}"
fallback_to_default_config venv_folder
fallback_to_default_config extract_kraken2_outdir
fallback_to_default_config extract_output_dir
fallback_to_default_config metadata_file

# --- Resolve taxon label and reference accession ---
taxon_label="${taxon_arg:-${extract_taxon_label:-cladeii}}"

case "${taxon_label,,}" in
    cladei|cladeia|mpox_cladei|mpox_cladeia|mpox-clade-i|mpox-clade-ia|mpox-cladei|mpox-cladeia)
        ref_accession="${ref_arg:-NC_003310.1}"
        taxon_label="mpox_cladeia"
        taxon_taxid="10244"
        taxon_sci_name="Monkeypox virus"
        ;;
    cladeib|mpox_cladeib|mpox-clade-ib|mpox-cladeib)
        ref_accession="${ref_arg:-PP899475.1}"
        taxon_label="mpox_cladeib"
        taxon_taxid="10244"
        taxon_sci_name="Monkeypox virus"
        ;;
    cladeii|mpox_cladeii|mpox-clade-ii|mpox-cladeii)
        ref_accession="${ref_arg:-NC_063383.1}"
        taxon_label="mpox_cladeii"
        taxon_taxid="10244"
        taxon_sci_name="Monkeypox virus"
        ;;
    *)
        ref_accession="${ref_arg}"
        taxon_taxid=""
        taxon_sci_name=""
        if [ -z "${ref_accession}" ]; then
            echo -e "\033[0;31mError: ref_accession is required for taxon '${taxon_label}'."
            echo -e "Usage: $0 [kraken2_outdir] [output_dir] [taxon_label] [ref_accession]\033[0m"
            exit 1
        fi
        ;;
esac

echo -e "\nTarget taxon:  ${taxon_label}"
echo -e "Reference:     ${ref_accession}"

# --- Resolve kraken2 output directory ---
if [ -n "${kraken2_outdir_arg}" ]; then
    kraken2_outdir=$(resolve_path "${SCRIPT_DIR}" "${kraken2_outdir_arg}")
else
    kraken2_outdir=$(get_path "Enter path to kraken2 output directory (kraken2/db2/)" "${mpox_kraken2_outdir}" "" "directory") || exit $?
fi

if [ ! -d "${kraken2_outdir}" ]; then
    echo -e "\033[0;31mError: Directory not found: ${kraken2_outdir}\033[0m"
    exit 1
fi

# --- Auto-detect input files ---
# When barcode_filter is set (e.g. "barcode16"), restrict to that barcode's files.
# Without a filter, a directory containing multiple barcodes would silently process
# only the first file alphabetically — which is almost certainly wrong.
if [ -n "${barcode_filter}" ]; then
    _fastq_pattern="${barcode_filter}*.classified.fastq.gz"
    _report_pattern="${barcode_filter}*.report.txt"
else
    _fastq_pattern="*.classified.fastq.gz"
    _report_pattern="*.report.txt"
fi

classified_fastq=$(find "${kraken2_outdir}" -maxdepth 1 -name "${_fastq_pattern}" | sort | head -1)
report_file=$(find "${kraken2_outdir}" -maxdepth 1 -name "${_report_pattern}" | sort | head -1)

if [ -z "${classified_fastq}" ]; then
    echo -e "\033[0;31mError: No .classified.fastq.gz found in ${kraken2_outdir}${barcode_filter:+ matching '${barcode_filter}*'}\033[0m"
    echo "Did you run taxprofiler with --kraken2_save_reads?"
    exit 1
fi

# Guard: if no filter was given and multiple fastq files exist, something is wrong.
if [ -z "${barcode_filter}" ]; then
    _fastq_count=$(find "${kraken2_outdir}" -maxdepth 1 -name "*.classified.fastq.gz" | wc -l)
    if [ "${_fastq_count}" -gt 1 ]; then
        echo -e "\033[0;31mError: ${_fastq_count} .classified.fastq.gz files found in ${kraken2_outdir} but no barcode filter was given.\033[0m"
        echo -e "Pass a barcode name as the 5th argument (e.g. 'barcode16'), or call this script once per barcode."
        exit 1
    fi
fi

if [ -z "${report_file}" ]; then
    echo -e "\033[0;31mError: No .report.txt found in ${kraken2_outdir}\033[0m"
    exit 1
fi

echo -e "Found classified reads: ${classified_fastq}"
echo "Found Kraken2 report:   ${report_file}"

# --- Resolve output directory ---
if [ -n "${output_dir_arg}" ]; then
    output_dir=$(resolve_path "${SCRIPT_DIR}" "${output_dir_arg}")
else
    default_output_dir="$(dirname "$(dirname "${kraken2_outdir}")")/${taxon_label}_analysis"
    output_dir=$(get_path "Enter output directory" "${default_output_dir}" "" "none") || exit $?
fi

mkdir -p "${output_dir}"

# Save paths to config for next run
set_config_value "${CONFIG_FILE}" extract_kraken2_outdir "${kraken2_outdir}"
set_config_value "${CONFIG_FILE}" extract_output_dir "${output_dir}"
set_config_value "${CONFIG_FILE}" extract_taxon_label "${taxon_label}"

# Derive sample name from the classified fastq filename
sample_name=$(basename "${classified_fastq}" | sed 's/\.kraken2\.classified\.fastq\.gz//')
# Taxprofiler appends the database name (e.g. _db2) before the extension; strip it
sample_name=$(echo "${sample_name}" | sed 's/_db[0-9]*$//')

output_fastq="${output_dir}/${sample_name}.${taxon_label}.fastq"
output_bam="${output_dir}/${sample_name}.${taxon_label}.bam"
output_report="${output_dir}/${sample_name}.${taxon_label}_confidence_report.txt"
ref_fasta="${REF_CACHE_DIR}/${ref_accession}.fasta"

# --- Parse barcode and run_accession from sample_name ---
# sample_name format: barcode11_20250923_1409_MN37872_FBD41729_fca07934
barcode_id="${sample_name%%_*}"
run_accession_id="${sample_name#${barcode_id}_}"

# =============================================================================
# METADATA LOOKUP
# =============================================================================
echo -e "\n--- Metadata lookup ---"

META_FOUND="no"
META_SAMPLE_CODE=""
META_SAMPLE_ID=""
META_SAMPLE_TYPE_CODE=""
META_SAMPLE_TYPE_DESC=""
META_SAMPLING_DATE=""
META_SITE_ID=""
META_SITE=""
META_CITY=""
META_COUNTRY=""
META_PARTNER_CODE=""
META_COMMENTS=""

_lookup_metadata() {
    # Activate venv to get Python with pandas/openpyxl
    local _python=""
    if [ -n "${venv_folder}" ] && [ -f "${venv_folder}/bin/activate" ]; then
        source "${venv_folder}/bin/activate" 2>/dev/null
    fi
    if command -v python &>/dev/null; then
        _python="python"
    else
        echo -e "\033[0;33mWarning: Python not found — skipping metadata lookup.\033[0m"
        return 1
    fi

    if [ -z "${metadata_file}" ]; then
        echo -e "\033[0;33mWarning: metadata_file not set in config — skipping metadata lookup.\033[0m"
        echo -e "\033[0;33mRun any pipeline script once to set it, or add: metadata_file=<path> to ${CONFIG_FILE}\033[0m"
        return 1
    fi

    local meta_path
    meta_path=$(resolve_path "${SCRIPT_DIR}" "${metadata_file}")
    if [ ! -f "${meta_path}" ]; then
        echo -e "\033[0;33mWarning: Metadata file not found: ${meta_path}\033[0m"
        return 1
    fi

    local lookup_script="${SCRIPT_DIR}/lookup_sample_metadata.py"
    if [ ! -f "${lookup_script}" ]; then
        echo -e "\033[0;33mWarning: ${lookup_script} not found — skipping metadata lookup.\033[0m"
        return 1
    fi

    local output
    output=$("${_python}" "${lookup_script}" "${meta_path}" "${barcode_id}" "${run_accession_id}" "${SCRIPT_DIR}" 2>/dev/null)

    if [ -z "${output}" ]; then
        echo -e "\033[0;33mWarning: Metadata lookup returned no output.\033[0m"
        return 1
    fi

    # Eval the KEY=VALUE lines from the Python script into shell variables
    while IFS= read -r line; do
        case "${line}" in
            META_*)
                export "${line?}"
                ;;
        esac
    done <<< "${output}"
}

_lookup_metadata

case "${META_FOUND}" in
    yes)
        echo -e "\033[0;32mMetadata found: ${META_SAMPLE_CODE} / ${META_SAMPLING_DATE} / ${META_COUNTRY}\033[0m"
        ;;
    no)
        echo -e "\033[0;33mNo metadata row found for barcode='${barcode_id}', run='${run_accession_id}'.\033[0m"
        ;;
    error)
        echo -e "\033[0;33mMetadata lookup error: ${META_ERROR}\033[0m"
        ;;
esac

# --- Check required tools ---
_locate_tool() {
    local tool="$1"
    command -v "${tool}" &>/dev/null && return 0
    local conda_base="${HOME}/miniforge3"
    for env_bin in \
        "${conda_base}/bin" \
        "${conda_base}/envs/squirrel/bin" \
        "${conda_base}/envs/artic/bin" \
        "${conda_base}/envs/base/bin"
    do
        if [ -x "${env_bin}/${tool}" ]; then
            export PATH="${env_bin}:${PATH}"
            echo -e "\033[0;32mFound ${tool} in ${env_bin}\033[0m" >&2
            return 0
        fi
    done
    return 1
}

missing_tools=()
for tool in minimap2 samtools; do
    if ! _locate_tool "${tool}"; then
        missing_tools+=("${tool}")
    fi
done

if [ ${#missing_tools[@]} -gt 0 ]; then
    echo -e "\033[0;31mError: Required tools not found: ${missing_tools[*]}\033[0m"
    echo -e "Install via one of:"
    echo -e "  sudo apt install minimap2 samtools"
    echo -e "  conda install -n base -c bioconda minimap2 samtools"
    echo -e "  conda activate squirrel  (if artic/squirrel env is set up)"
    exit 1
fi

# --- Fetch reference genome if not cached ---
mkdir -p "${REF_CACHE_DIR}"
if [ ! -f "${ref_fasta}" ]; then
    echo -e "\nDownloading reference genome ${ref_accession} from NCBI..."
    _curl_ca_opt=""
    [ -n "${_NORCE_CA}" ] && _curl_ca_opt="--cacert ${_NORCE_CA}"
    curl -fsSL ${_curl_ca_opt} \
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=${ref_accession}&rettype=fasta&retmode=text" \
        -o "${ref_fasta}" || {
        echo -e "\033[0;31mError: Failed to download reference ${ref_accession}. Check network/proxy.\033[0m"
        exit 1
    }
    echo "Reference saved to: ${ref_fasta}"
else
    echo -e "\nUsing cached reference: ${ref_fasta}"
fi

# =============================================================================
# STEP 1: Align ALL classified reads to the target reference
# =============================================================================
echo -e "\n--- Step 1: Aligning classified reads to ${ref_accession} with minimap2 ---"

_all_bam="${output_dir}/${sample_name}.all_classified.bam"
minimap2 -ax map-ont -t 4 "${ref_fasta}" "${classified_fastq}" \
    | samtools sort -o "${_all_bam}"

if [ $? -ne 0 ]; then
    echo -e "\033[0;31mError: Alignment failed.\033[0m"
    exit 1
fi
samtools index "${_all_bam}"

# =============================================================================
# STEP 2: Extract reads that mapped to the reference
# =============================================================================
echo -e "\n--- Step 2: Extracting ${taxon_label}-mapped reads ---"

samtools view -b -F 4 "${_all_bam}" > "${output_bam}"
samtools index "${output_bam}"
samtools fastq "${output_bam}" > "${output_fastq}"

read_count=$(grep -c "^@" "${output_fastq}" 2>/dev/null || echo 0)
echo -e "Reads mapped to ${ref_accession}: ${read_count}"

rm -f "${_all_bam}" "${_all_bam}.bai"

# --- Build the sample metadata block for the report ---
_meta_block() {
    if [ "${META_FOUND}" = "yes" ]; then
        echo "Sample metadata"
        echo "---------------"
        echo "Sample code:         ${META_SAMPLE_CODE}"
        echo "Sample ID:           ${META_SAMPLE_ID}"
        echo "Sample type:         ${META_SAMPLE_TYPE_CODE}  —  ${META_SAMPLE_TYPE_DESC}"
        echo "Sampling date:       ${META_SAMPLING_DATE}"
        echo "Site:                ${META_SITE_ID}  ${META_SITE:+/ ${META_SITE}}"
        echo "Location:            ${META_CITY:+${META_CITY}, }${META_COUNTRY}"
        [ -n "${META_PARTNER_CODE}" ] && echo "Partner sample code: ${META_PARTNER_CODE}"
        [ -n "${META_COMMENTS}" ]     && echo "Sampling notes:      ${META_COMMENTS}"
    else
        echo "Sample metadata"
        echo "---------------"
        echo "Barcode:             ${barcode_id}"
        echo "Run accession:       ${run_accession_id}"
        if [ "${META_FOUND}" = "no" ]; then
            echo "(No metadata record found for this barcode / run combination)"
        else
            echo "(Metadata lookup failed: ${META_ERROR:-unknown error})"
        fi
    fi
}

if [ "${read_count}" -eq 0 ]; then
    echo -e "\033[0;33mNo reads mapped to ${ref_accession}. Writing report.\033[0m"
    cat > "${output_report}" <<EOF
Read Extraction and Alignment Confidence Report
===============================================
Taxon:           ${taxon_label}
Reference:       ${ref_accession}
Barcode:         ${barcode_id}
Run:             ${run_accession_id}
Report date:     $(date '+%Y-%m-%d %H:%M:%S')

$(_meta_block)

Input files
-----------
Kraken2 report:   ${report_file}
Classified FASTQ: ${classified_fastq}

RESULT: No reads from the Kraken2 classified set mapped to ${ref_accession}.
EOF
    echo -e "\033[0;33mReport written to: ${output_report}\033[0m"
    exit 0
fi

# =============================================================================
# STEP 3: Coverage statistics
# =============================================================================
echo -e "\n--- Step 3: Computing coverage statistics ---"

coverage_tsv=$(samtools coverage "${output_bam}")

mapped_reads=$(echo "${coverage_tsv}" | awk 'NR>1 {print $4}' | head -1)
cov_bases=$(echo "${coverage_tsv}"    | awk 'NR>1 {print $5}' | head -1)
pct_covered=$(echo "${coverage_tsv}"  | awk 'NR>1 {print $6}' | head -1)
mean_depth=$(echo "${coverage_tsv}"   | awk 'NR>1 {print $7}' | head -1)
mean_mapq=$(echo "${coverage_tsv}"    | awk 'NR>1 {print $9}' | head -1)
ref_length=$(samtools view -H "${output_bam}" | awk '/^@SQ/ {match($0,/LN:([0-9]+)/,a); print a[1]}' | head -1)

if [ -n "${taxon_taxid}" ]; then
    kraken_taxon_count=$(awk -v tid="${taxon_taxid}" '$5 == tid {sum+=$2} END {print sum+0}' "${report_file}")
else
    kraken_taxon_count=$(awk -v pat="${taxon_label}" 'tolower($6) ~ tolower(pat) {sum+=$2} END {print sum+0}' "${report_file}")
fi

# =============================================================================
# STEP 4: Write confidence report
# =============================================================================
echo -e "\n--- Step 4: Writing confidence report ---"

cat > "${output_report}" <<EOF
Read Extraction and Alignment Confidence Report
===============================================
Taxon:               ${taxon_label}
Reference:           ${ref_accession}
Reference length:    ${ref_length:-unknown} bp
Barcode:             ${barcode_id}
Run:                 ${run_accession_id}
Report date:         $(date '+%Y-%m-%d %H:%M:%S')

$(_meta_block)

Input files
-----------
Kraken2 report:      ${report_file}
Classified FASTQ:    ${classified_fastq}
Reference FASTA:     ${ref_fasta}

Kraken2 classification
----------------------
Reads classified as taxid ${taxon_taxid:-${taxon_label}}${taxon_sci_name:+ (${taxon_sci_name})}: ${kraken_taxon_count}

Alignment to reference (minimap2 map-ont)
-----------------------------------------
All Kraken2-classified reads aligned to ${ref_accession}.
Reads that mapped (extracted as ${taxon_label} candidates): ${read_count}
Reference bases covered:   ${cov_bases} / ${ref_length:-?} bp  (${pct_covered}%)
Mean sequencing depth:     ${mean_depth}x
Mean mapping quality:      ${mean_mapq}

Output files
------------
Extracted reads (FASTQ): ${output_fastq}
Alignment (BAM):         ${output_bam}
This report:             ${output_report}

Interpretation guidance
-----------------------
High confidence (genuine signal):
  - Genome coverage > 10% AND mean depth > 1x AND mean mapq > 20
  - Multiple reads aligned across distinct genome regions

Low confidence (possible noise or mis-classification):
  - Genome coverage < 5% with reads clustering in one region
  - Mean mapping quality < 20 (reads map equally well elsewhere)
  - Fewer than ~10 aligned reads

Note: This analysis uses reads assigned by Kraken2 during metagenomic screening.
It is intended as a screening indicator, not a diagnostic confirmation.
EOF

echo -e "\n\033[0;32m=== Summary ===\033[0m"
echo -e "\033[0;32mSample:               ${META_SAMPLE_CODE:-${barcode_id}}\033[0m"
echo -e "\033[0;32mReads extracted:      ${read_count}\033[0m"
echo -e "\033[0;32mReads aligned:        ${mapped_reads}\033[0m"
echo -e "\033[0;32mGenome coverage:      ${pct_covered}%\033[0m"
echo -e "\033[0;32mMean depth:           ${mean_depth}x\033[0m"
echo -e "\033[0;32mMean mapping quality: ${mean_mapq}\033[0m"
echo -e "\n\033[0;32mOutputs written to: ${output_dir}\033[0m"
echo -e "\033[0;32mConfidence report:  ${output_report}\033[0m\n"
