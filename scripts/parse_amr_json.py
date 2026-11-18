#!/usr/bin/env python3
"""
Parse AMR JSON files from Nextflow wf-metagenomics output and create a pandas DataFrame.

Updated: Now only reads AMR JSON files for run_accessions/barcodes present in the provided metadata Excel.
Directory discovery mirrors logic in create_kraken_datasets.py but uses
'nanopore_processed/outputs_wf_metagenomics_amr/<dir_option>'.
"""

import argparse
import glob
import json
import logging
import os
import sys
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# amr_data columns, in order. Metadata columns that are empty hold '' (never NaN), lon/lat
# excepted, which stay numeric. sample_key identifies one sample: sample_id and sampling date.
AMR_COLUMNS = [
    'run_accession', 'barcode', 'pass_status', 'gene_description', 'multi_resistance', 'resistance',
    'short_name', 'read_count', 'alignment_count', 'classified_reads', 'total_reads',
    'coverage_percent', 'identity_percent', 'file', 'incomplete_data', 'protocol_id',
    'sequencing_kit_id', 'type', 'replicate', 'replicate_type', 'runName', 'sampleName', 'alias',
    'sample_code', 'sample_id', 'sample_key', 'sampling_date', 'sampling_site_id', 'sample_type',
    'country', 'lon', 'lat',
]
_TEXT_METADATA = ['protocol_id', 'sequencing_kit_id', 'type', 'replicate_type', 'runName', 'sampleName',
                  'alias', 'sample_code', 'sample_id', 'sample_key', 'sampling_date', 'sampling_site_id',
                  'sample_type', 'country']

from kraken_parser import read_kraken2_report

from nanopore_metadata import (
    read_nanopore_metadata,
    load_sites_df,
    load_sample_lookup,
    site_and_type,
    get_connected_run_accessions,
    merge_with_existing_file,
    warn_list,
)
from replicates import (
    AMR_REPLICATES_PER_BARCODE,
    AMR_REPLICATES_POOL,
    pooled_metadata_df,
    replicate_label,
    replicate_problems,
)

# ── Short-code helpers ────────────────────────────────────────────────────────
# short_name is a display abbreviation of the `resistance` value in the same record.
# It carries no information that column does not, so `resistance` is always the
# source of truth; short_name exists only because full drug-class names do not fit
# on a chart axis.
#
# JOIN KEY — codes are assigned per dataset, and a code lengthens only when a colliding
# class is present in that dataset, so one class may carry different codes in two
# feathers; a fixed code table kept elsewhere (e.g. by a figure script) agrees with these
# codes only on the data it was made from. Consumers
# join and group on `resistance`, never on `short_name`.
#
# 'y' counts as a vowel. It is a consonant in "glycopeptide" only by spelling, and
# treating it as one collapses that class and "glycylcycline" onto the same code.
_VOWELS = frozenset("aeiouy")


def _consonant_skeleton(name: str) -> str:
    """First letter followed by every consonant after it."""
    return name[0] + "".join(c for c in name[1:] if c.isalpha() and c not in _VOWELS)


def _code_candidates(name: str):
    """Codes for `name`, best first.

    The first choice is the usual four characters. Where that is already taken, the
    fourth character is replaced by the *next* consonant rather than a fifth being
    appended, so codes stay one width and line up on an axis::

        cephalosporin  c p h | l s p r n   ->  cphl, then cphs, cphp, cphr, cphn
        cephalexin     c p h | l x n       ->  cphl, then cphx, cphn

    Only once every consonant has been tried does the code lengthen, and that is a
    backstop rather than the normal path.

    A name with fewer than four consonants (e.g. "penam" -> "pnm") cannot fill four
    characters from its skeleton, so the plain name is used instead; that keeps
    "penam" and "penem" apart without naming either of them in the code.
    """
    skeleton = _consonant_skeleton(name)
    base = skeleton if len(skeleton) >= 4 else name
    prefix = base[:3]
    for char in base[3:]:                       # same width, later consonant
        yield prefix + char
    for length in range(5, len(base) + 1):      # backstop: lengthen
        yield base[:length]
    yield base.ljust(4, "x")


def assign_drug_codes(names) -> dict:
    """Map each drug-class name to a short code, lengthening to avoid collisions.

    Four characters where that is unambiguous; where two classes would share a code
    the later one takes another consonant, and so on ("cephalosporin" -> 'cphl',
    "cephalexin" -> 'cphlx'). Nothing about the vocabulary is hard-coded, so a study
    with entirely different drug classes is handled the same way.

    Names are sorted before codes are handed out, so the mapping depends only on
    *which* classes are present, never on the order the files happened to be read
    in. It does still depend on the set: a class that shares a 4-character code with
    another only lengthens when that other class is present too. Codes are therefore
    comparable within a dataset, and `resistance` remains the key to use across them.
    """
    codes, taken = {}, set()
    for name in sorted({n for n in names if n}):
        for candidate in _code_candidates(name.lower().strip()):
            if candidate not in taken:
                codes[name] = candidate
                taken.add(candidate)
                break
        else:
            codes[name] = next(iter(_code_candidates(name.lower().strip())))
    return codes


def _make_drug_code(name: str) -> str:
    """The 4-character code for one name, with no collision resolution.

    Only meaningful for a single name in isolation; use assign_drug_codes() when
    several classes are in play, because that is what lengthens a colliding code.
    """
    name = name.lower().strip()
    if not name:
        return ""
    return next(iter(_code_candidates(name)))


def _codes_are_distinct(names) -> dict:
    """Return {code: [names]} for every code that more than one name maps to.

    Uses assign_drug_codes(), so this reports only collisions that lengthening
    could not resolve — two classes with the same consonant skeleton.
    """
    codes = assign_drug_codes(names)
    by_code = {}
    for name, code in codes.items():
        by_code.setdefault(code, []).append(name)
    return {c: sorted(n) for c, n in by_code.items() if len(n) > 1}


def add_short_names(df: pd.DataFrame) -> pd.DataFrame:
    """Fill ``short_name`` from every drug class present in ``df``.

    Codes have to be assigned over the whole dataset, not one file at a time: a
    class that only appears in one barcode still has to get the same code as it
    would anywhere else in the same feather.
    """
    if df.empty or 'resistance' not in df.columns:
        return df
    classes = {t.strip() for value in df['resistance'].dropna()
               for t in str(value).split(';') if t.strip()}
    codes = assign_drug_codes(classes)
    unresolved = _codes_are_distinct(classes)
    if unresolved:
        logger.warning(
            f"Drug classes share a short code even after lengthening: {unresolved}. "
            f"short_name is ambiguous for these; group on 'resistance' instead."
        )
    df['short_name'] = df['resistance'].map(
        lambda v: ';'.join(codes.get(t.strip(), '') for t in str(v).split(';') if t.strip())
        if pd.notna(v) else None
    )
    return df


# -- Read counts --------------------------------------------------------------
# wf-metagenomics reports one entry in a gene's ``meta`` list per alignment, and repeats
# the gene's total in ``count`` on every one of them. One row per alignment would
# therefore carry a column that is already a total, and summing it over the rows of a
# gene squares the read count. The parser aggregates the alignments instead and emits one
# row per (barcode, gene, drug-class profile), so every count on a row is that row's own
# and sums correctly.
#
# ``SEQUENCE`` is the read identifier, not a reference accession. One read can align to a
# gene more than once, so alignments overstate reads and the two are counted separately.
#
# A gene's ``meta`` entries do not all have to agree on ``RESISTANCE``: CARD descriptions
# such as "From the Lahey list of beta-lactamases." are shared by several genes, and the
# workflow keys ``results`` on the description. ``resistance`` is part of the row key so
# those stay apart, because ``count`` alone could not be split between them.

KRAKEN2_COLUMN_NAMES = [
    "Pct. of Frags",
    "No of Frags root",
    "No of Frags",
    "Rank code",
    "NCBI tax ID",
    "Scientific name",
]


def _distinct_reads(hits: list[dict]) -> int:
    """How many reads produced these alignments.

    Alignments carrying the same ``SEQUENCE`` come from one read. An alignment with no
    identifier cannot be matched to any other and counts as one read of its own.
    """
    identified = {h["SEQUENCE"] for h in hits if h.get("SEQUENCE")}
    anonymous = sum(1 for h in hits if not h.get("SEQUENCE"))
    return len(identified) + anonymous


def _mean(values) -> float | None:
    """Mean of the numeric values, or None when there are none."""
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(numbers) / len(numbers) if numbers else None


def _kraken2_report_beside(amr_json_path: str, barcode: str) -> str:
    """The barcode's Kraken2 report from the same wf-metagenomics AMR run.

    ``<run>/amr/<barcode>.amr.json`` sits beside ``<run>/kraken2/<barcode>.kraken2.report.txt``
    — the same reads, classified by the same run with the same database.

    Raises when the run wrote no such report. ``--amr`` always runs the classification
    step, so a missing report means the output directory is not the one it looks like,
    and a read count nobody can normalise is worse than no row at all.
    """
    run_dir = os.path.dirname(os.path.dirname(os.path.abspath(amr_json_path)))
    candidate = os.path.join(run_dir, "kraken2", f"{barcode}.kraken2.report.txt")
    if not os.path.isfile(candidate):
        raise FileNotFoundError(
            f"No Kraken2 report for barcode '{barcode}': expected '{candidate}' beside "
            f"'{amr_json_path}'. It is the only denominator for rpm — a taxprofiler run "
            f"over the same reads classifies a several-fold different number of them."
        )
    return candidate


def read_barcode_read_totals(report_path: str) -> tuple[int, int]:
    """The two read totals for one barcode, from its Kraken2 report.

    Returns ``(classified_reads, total_reads)``: the clade count on the root row
    (NCBI tax ID 1), and that plus the unclassified row (tax ID 0) — every read the step
    was given.

    Both are written to the feather and neither is turned into a rate here. Which of them
    normalises the AMR counts is a question about what the numerator is commensurate
    with, and the figures answer it: a stored ratio would fix one answer into the file,
    and no later analysis could get the raw numbers back. The taxonomy datasets store
    ``No of Frags root`` the same way and let the consumer form RPM.

    The share Kraken2 can classify varies from 2% to 95% across these barcodes, so the
    two totals are not interchangeable and the column names say which is which.

    Only the AMR run's own report answers this. A taxprofiler run over the same input
    classifies a different number of reads — several-fold different, and by a factor that
    varies per barcode — so its totals are not a substitute.

    Raises when the report cannot be read, has no root row, or covers no reads at all.
    """
    report = read_kraken2_report(report_path, KRAKEN2_COLUMN_NAMES)
    root = report[report["NCBI tax ID"] == 1]
    if root.empty:
        raise ValueError(
            f"Kraken2 report has no root row (tax ID 1), so it gives no read total to "
            f"normalise against: '{report_path}'"
        )
    classified = int(root["No of Frags root"].iloc[0])
    unclassified_row = report[report["NCBI tax ID"] == 0]
    unclassified = int(unclassified_row["No of Frags root"].iloc[0]) if not unclassified_row.empty else 0
    total = classified + unclassified
    if total <= 0:
        raise ValueError(
            f"Kraken2 report covers no reads at all, so there is nothing to normalise "
            f"against, yet the AMR output lists genes for this barcode: '{report_path}'"
        )
    return classified, total


# ── JSON parsing ──────────────────────────────────────────────────────────────


def parse_amr_json_file(file_path, run_accession=None):
    """
    Parse a single AMR JSON file and extract data.

    Returns one record per (barcode, gene, drug-class profile), with the gene's alignments
    aggregated into ``read_count`` and ``alignment_count``. A barcode in which the workflow
    found no gene at all gets one row of its own, carrying the read totals and nothing else,
    so that it can be counted as analysed.

``classified_reads`` and ``total_reads`` come from the Kraken2 report the same AMR run
    wrote beside the JSON. Both are raw counts: the rate is formed by whoever normalises,
    not stored here. A barcode with genes but no readable report raises, so every row
    carries real read totals or none is written.

    Args:
        file_path (str): Path to the JSON file
        run_accession (str): Identifier for the run (parent folder of 'amr')

    Returns:
        list: List of dictionaries containing the parsed data
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []
    records = []
    for barcode_key, barcode_data in data.items():
        if not isinstance(barcode_data, dict):
            continue
        pass_status = barcode_data.get('pass', None)
        results = barcode_data.get('results', {})
        if not results:
            # ``pass`` is False exactly when abricate's results table was empty, so this
            # barcode is a measurement — no gene cleared the identity and coverage
            # thresholds — rather than a gap. One row records it, with no gene and no
            # reads, so a denominator can count the barcode and tell "nothing found"
            # from "not analysed". Without it every count drawn from this file is of
            # barcodes that detected something, which is not the same question.
            #
            # It needs the read totals as much as any other row: "no gene in 47 reads"
            # and "no gene in a million" are different findings, and only the report
            # separates them. Where there is no readable report the barcode is skipped
            # rather than written with empty totals, keeping the guarantee that every
            # row carries real ones.
            try:
                classified_reads, total_reads = read_barcode_read_totals(
                    _kraken2_report_beside(file_path, barcode_key)
                )
            except (FileNotFoundError, ValueError) as e:
                print(
                    f"Warning: barcode '{barcode_key}' of '{file_path}' has no AMR gene and "
                    f"no usable read total, so it is not recorded and will be missing from "
                    f"any count of barcodes analysed: {e}"
                )
                continue
            records.append({
                'run_accession': run_accession,
                'barcode': barcode_key,
                'pass_status': pass_status,
                'gene_description': None,
                'multi_resistance': False,
                'resistance': None,
                'short_name': None,
                'read_count': 0,
                'alignment_count': 0,
                'classified_reads': classified_reads,
                'total_reads': total_reads,
                'coverage_percent': None,
                'identity_percent': None,
                'file': file_path,
            })
            continue
        classified_reads, total_reads = read_barcode_read_totals(
            _kraken2_report_beside(file_path, barcode_key)
        )
        for gene_description, gene_data in results.items():
            if not isinstance(gene_data, dict):
                continue
            by_resistance = {}
            for meta in gene_data.get('meta', []):
                by_resistance.setdefault(meta.get('RESISTANCE'), []).append(meta)
            for resistance_all, hits in by_resistance.items():
                resistance_tokens = resistance_all.split(';') if resistance_all else [None]
                reads = _distinct_reads(hits)
                records.append({
                    'run_accession': run_accession,
                    'barcode': barcode_key,
                    'pass_status': pass_status,
                    'gene_description': gene_description,
                    'multi_resistance': len(resistance_tokens) > 1 if resistance_tokens else False,
                    'resistance': resistance_all,
                    'short_name': None,  # filled by add_short_names() over the whole dataset
                    'read_count': reads,
                    'alignment_count': len(hits),
                    'classified_reads': classified_reads,
                    'total_reads': total_reads,
                    'coverage_percent': _mean(h.get('%COVERAGE') for h in hits),
                    'identity_percent': _mean(h.get('%IDENTITY') for h in hits),
                    'file': file_path,
                })
    return records


def _find_amr_files_for_barcode(base_path: str, barcode: str) -> List[str]:
    """Find AMR json files for a specific barcode within a discovered base_path.

    ``base_path`` is the one run directory chosen by the caller, so the workflow writes
    the barcode's JSON directly under ``amr/``. That exact location is authoritative: when
    it holds the file, nothing below it is searched, so a nested directory cannot
    contribute another run's output under this run's accession. The recursive pattern
    remains only as a fallback for a layout that nests the workflow output, and never
    leaves ``base_path``.
    """
    direct = os.path.join(base_path, 'amr', f'{barcode}.amr.json')
    if os.path.isfile(direct):
        return [direct]
    nested = glob.glob(
        os.path.join(base_path, '**', 'amr', f'{barcode}.amr.json'), recursive=True
    )
    return sorted(set(nested))


def create_amr_dataframe_from_metadata(metadata_file: str, data_folder: str,
                                       pool_replicates: bool = True) -> Tuple[pd.DataFrame, set]:
    """Build AMR dataframe based on metadata-defined run_accessions & barcodes.

    Mirrors directory selection logic from create_kraken_datasets.create_kraken_dataset_from_metadata
    but uses outputs_wf_metagenomics_amr.

    ``pool_replicates`` must say what the AMR run did (``amr_replicates``, as in odin_pipeline):
    pooled, a replicate group's JSON is named after its barcodes and is read once, under a row whose
    ``replicate`` is ``pooled``; per barcode, each member's JSON is read under its own row, which
    keeps its replicate number.

    Returns dataframe and set of processed run_accessions (original, not merged list).
    """
    sites_df = load_sites_df(metadata_file)
    sample_lookup = load_sample_lookup(metadata_file)
    metadata_df = read_nanopore_metadata(metadata_file)
    # Keep rows with non-empty barcode
    metadata_df = metadata_df.loc[
        (metadata_df['barcode'].notna()) & (metadata_df['barcode'].astype(str).str.strip() != '')]
    if pool_replicates:
        problems = replicate_problems(metadata_df.to_dict('records'))
        if problems:
            raise ValueError('Replicate groups that cannot be pooled:\n' + '\n'.join(problems))
    metadata_df = pooled_metadata_df(metadata_df, pool=pool_replicates)
    df_out = pd.DataFrame()
    missing_dirs = set()
    missing_files = set()
    missing_barcodes = set()
    empty_runs = set()
    processed_run_accessions = set()
    read_samples = set()
    logger.info(f'Creating AMR dataset from metadata: {metadata_file}. Rows with barcodes: {len(metadata_df)}')

    for _, row in metadata_df.iterrows():
        run_accession = str(row['run_accession'])
        barcode = str(row['barcode']).strip()
        if not barcode:
            missing_barcodes.add(run_accession)
            continue
        # Determine directory options order based on connected runs
        keep = get_connected_run_accessions(metadata_df, run_accession)
        connected_run_accessions = keep['run_accession'].unique() if not keep.empty else []
        if not keep.empty:
            dir_options = [str(row['sampleName']), f'merged_{run_accession}', run_accession]
        else:
            dir_options = [run_accession, str(row['sampleName']), f'merged_{run_accession}']
        # Build candidate directories
        candidate_dirs = [
            os.path.join(data_folder, 'nanopore_processed', 'outputs_wf_metagenomics_amr', opt)
            for opt in dir_options
        ]
        base_path = candidate_dirs[0]
        for cdir in candidate_dirs:
            if os.path.isdir(cdir):
                base_path = cdir
                break
        if not os.path.isdir(base_path):
            missing_dirs.add(run_accession)
            continue
        logger.info(
            f"Processing run_accession:{row['run_accession']}, barcode: {barcode}, sampleName: {row['sampleName']}, from directory: {base_path}")
        # Find amr json files for this barcode under base_path
        files = _find_amr_files_for_barcode(base_path, barcode)
        if not files:
            missing_files.add(run_accession)
            continue
        is_incomplete = (not keep.empty) and base_path.endswith(run_accession)
        # A merged set's rows carry its earliest loading (MinKNOW names start with the date).
        run_acc = run_accession if is_incomplete or keep.empty else min(connected_run_accessions)
        # A merged set has one metadata row per accession but one output; read each sample's
        # output once (the first row wins), as odin_pipeline does, so no row is counted twice.
        sample_key = (base_path, barcode, str(row.get('sample_code', '')), str(row.get('sampling_date', '')),
                      str(row.get('protocol_id', '')), str(row.get('sequencing_kit_id', '')))
        if sample_key in read_samples:
            processed_run_accessions.add(run_accession)
            continue
        read_samples.add(sample_key)
        for f in files:
            records = parse_amr_json_file(f, run_accession=run_acc)
            if not records:
                continue
            tmp_df = pd.DataFrame(records)
            tmp_df['incomplete_data'] = is_incomplete
            # attach basic metadata columns to allow later enrichment (avoid duplicate merges inflating rows)
            for meta_col in ['sample_id', 'sample_code', 'sampling_date', 'protocol_id', 'sequencing_kit_id', 'barcode',
                             'alias', 'type', 'runName', 'sampleName', 'run_accession', 'replicate',
                             'replicate_type']:
                if meta_col in row and meta_col not in tmp_df.columns:
                    tmp_df[meta_col] = row[meta_col]
            tmp_df['run_accession'] = run_acc
            df_out = pd.concat([df_out, tmp_df], axis=0)
        processed_run_accessions.add(run_accession)

    # Warn
    warn_list("Missing AMR directories for run_accessions:", missing_dirs)
    warn_list("No AMR JSON files for run_accessions (given barcode):", missing_files)
    warn_list("Missing barcode in metadata for run_accessions:", missing_barcodes)
    warn_list("Empty parsed AMR data for run_accessions:", empty_runs)

    if df_out.empty:
        return df_out, processed_run_accessions

    df_out = add_short_names(df_out)
    df_out['replicate'] = df_out['replicate'].map(replicate_label)

    # Deduplicate
    dedup_cols = [c for c in df_out.columns if c not in {'incomplete_data'}]
    df_out.drop_duplicates(subset=dedup_cols, inplace=True)

    # Enrich with site info
    df_out = merge_with_sites_df(df_out, sites_df, sample_lookup)
    return finish_amr_columns(df_out), processed_run_accessions


def finish_amr_columns(df: pd.DataFrame) -> pd.DataFrame:
    """amr_data in its published shape: sample_key added, empty text metadata as '', columns in
    AMR_COLUMNS order, and a fresh index."""
    df = df.copy()
    has_key = df['sample_id'].notna() & (df['sample_id'].astype(str) != '')         & df['sampling_date'].notna() & (df['sampling_date'].astype(str) != '')
    df['sample_key'] = (df['sample_id'].astype(str) + '_' + df['sampling_date'].astype(str)).where(has_key, '')
    for col in _TEXT_METADATA:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].where(df[col].notna(), '')
    for col in ('lon', 'lat'):
        if col not in df.columns:
            df[col] = None
    extra = [c for c in df.columns if c not in AMR_COLUMNS]
    return df[[c for c in AMR_COLUMNS if c in df.columns] + extra].reset_index(drop=True)


def merge_with_sites_df(df: pd.DataFrame, sites_df: pd.DataFrame,
                        sample_lookup: dict | None = None) -> pd.DataFrame:
    """Add sampling_site_id, sample_type, country, lon and lat to each sample's rows.

    The site and the type come from the samples sheet by ``sample_code`` (``sample_lookup``, see
    nanopore_metadata.load_sample_lookup), as in odin_pipeline; a sample missing there falls back
    to parsing ``sample_id``.
    """
    df['country'] = None
    df['lon'] = None
    df['lat'] = None
    if sites_df.empty:
        print("Sites DataFrame is empty; skipping merge.")
        return df
    sample_ids = df.get('sample_id')
    if sample_ids is None:
        return df
    sample_ids = sample_ids.unique()
    for sample_id in sample_ids:
        if pd.isna(sample_id):
            continue
        mask = df['sample_id'] == sample_id
        sample_code = df.loc[mask, 'sample_code'].iloc[0] if 'sample_code' in df.columns else None
        sampling_site_id, sample_type = site_and_type(sample_code, sample_id, sample_lookup)
        if sampling_site_id:
            df.loc[mask, 'sample_type'] = sample_type
            df.loc[mask, 'sampling_site_id'] = sampling_site_id
            site_row = sites_df[sites_df['site_ID'] == sampling_site_id]
            if site_row.empty:
                logger.warning(f'No site found for sampling_site_id: {sampling_site_id}')
                continue
            df.loc[mask, 'country'] = site_row.iloc[0]['country']
            df.loc[mask, 'lon'] = site_row.iloc[0]['longitude']
            df.loc[mask, 'lat'] = site_row.iloc[0]['latitude']
    return df


def summarise_by_resistance(df: pd.DataFrame) -> pd.DataFrame:
    """One row per resistance profile, sorted by it.

    ``n_detections`` is the number of gene rows of amr_data carrying the profile. It counts
    genes, not reads: ``read_count`` beside it holds the reads, and the two differ by orders of
    magnitude. ``run_accession`` and ``barcode`` are distinct counts, ``read_count`` and
    ``alignment_count`` sums, the percentages means, and ``sample_code`` lists the sites.
    """
    agg_spec = {'run_accession': 'nunique', 'barcode': 'nunique'}
    for col, agg in (('read_count', 'sum'), ('alignment_count', 'sum'),
                     ('coverage_percent', 'mean'), ('identity_percent', 'mean')):
        if col in df.columns:
            agg_spec[col] = agg
    if 'sample_code' in df.columns:
        agg_spec['sample_code'] = lambda x: '; '.join(sorted(set(x.dropna().astype(str))))
    grouped = df.groupby('resistance')
    summary = grouped.agg(agg_spec).round(2)
    summary.insert(0, 'n_detections', grouped.size())
    summary.sort_index(inplace=True)
    return summary.reset_index()


def create_summary(df: pd.DataFrame, out_dir: str, file_prefix: str):
    """Write {file_prefix}_summary_by_resistance as .csv, .feather and .xlsx in out_dir."""
    if 'resistance' not in df.columns:
        return
    summary = summarise_by_resistance(df)
    if not (out_dir and file_prefix):
        return
    file = f"{out_dir}/{file_prefix}_summary_by_resistance.csv"
    summary.to_csv(file, index=False)
    print(f"Summary saved to: {file}")
    try:
        summary.to_feather(file.replace('.csv', '.feather'))
    except Exception as e:
        print(f"Warning: could not save feather summary ({e})")
    try:
        summary.to_excel(file.replace('.csv', '.xlsx'), index=False)
    except Exception as e:
        print(f"Warning: could not save excel summary ({e})")


def main():
    parser = argparse.ArgumentParser(
        description="Parse AMR JSON files from Nextflow wf-metagenomics output using metadata-driven directory discovery"
    )
    parser.add_argument('--data_path', required=True, help='Root data path containing nanopore_processed directory')
    parser.add_argument('--metadata_excel', required=True, help='Metadata Excel file path')
    parser.add_argument('-o', '--output', required=True, help='Output directory path (will create amr_data.* files)')
    parser.add_argument('--show-summary', action='store_true', help='Show summary statistics')
    parser.add_argument('--amr-replicates', choices=[AMR_REPLICATES_POOL, AMR_REPLICATES_PER_BARCODE],
                        default=AMR_REPLICATES_POOL,
                        help='What the AMR run did with replicate barcodes of one sample: pooled them before '
                             'screening (default, as in odin_pipeline) or screened each barcode. Must match '
                             'the run (start_nextflow_amr.sh --amr-replicates).')
    args = parser.parse_args()

    data_path = args.data_path
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(data_path):
        print(f"Error: data_path '{data_path}' does not exist")
        sys.exit(1)
    if not os.path.exists(args.metadata_excel):
        print(f"Error: metadata_excel '{args.metadata_excel}' does not exist")
        sys.exit(1)
    # Ensure output directory exists
    if os.path.isfile(output_dir):
        print(f"Error: --output must be a directory path, got existing file: {output_dir}")
        sys.exit(1)
    os.makedirs(output_dir, exist_ok=True)

    try:
        df, run_accessions = create_amr_dataframe_from_metadata(
            args.metadata_excel, data_path, pool_replicates=args.amr_replicates == AMR_REPLICATES_POOL)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    if df.empty:
        print('No AMR JSON data found for metadata run_accessions/barcodes')
        sys.exit(1)

    # Merge with existing feather main dataset if exists
    feather_path = os.path.join(output_dir, 'amr_data.feather')
    df = finish_amr_columns(merge_with_existing_file(df, run_accessions, feather_path))

    if args.show_summary:
        print('\n' + '=' * 50)
        print('SUMMARY STATISTICS')
        print('=' * 50)
        print(f'Total records: {len(df)}')
        print(f'Unique run_accessions: {df["run_accession"].nunique()}')
        print(f'Unique barcodes: {df["barcode"].nunique()}')
        if 'resistance' in df.columns:
            print(f'Unique resistance types: {df["resistance"].nunique()}')
        if 'pass_status' in df.columns:
            print('Pass status distribution:')
            print(df['pass_status'].value_counts())
        if 'resistance' in df.columns:
            print('\nTop 5 resistance types:')
            print(df['resistance'].value_counts().head())
        if 'barcode' in df.columns:
            print('\nResistance records per barcode:')
            print(df['barcode'].value_counts().head())
        if 'coverage_percent' in df.columns:
            try:
                print(f'\nAverage coverage: {pd.to_numeric(df["coverage_percent"], errors="coerce").mean():.2f}%')
            except Exception:
                pass
        if 'identity_percent' in df.columns:
            try:
                print(f'Average identity: {pd.to_numeric(df["identity_percent"], errors="coerce").mean():.2f}%')
            except Exception:
                pass

    # Standard output filenames
    csv_path = os.path.join(output_dir, 'amr_data.csv')
    feather_path = os.path.join(output_dir, 'amr_data.feather')
    excel_path = os.path.join(output_dir, 'amr_data.xlsx')

    try:
        df.to_csv(csv_path, index=False)
        print(f'Data saved to CSV: {csv_path}')
    except Exception as e:
        print(f'Warning: could not save CSV file ({e})')
    try:
        df.to_feather(feather_path)
        print(f'Data saved to Feather: {feather_path}')
    except Exception as e:
        print(f'Warning: could not save Feather file ({e})')
    try:
        df.to_excel(excel_path, index=False)
        print(f'Data saved to Excel: {excel_path}')
    except Exception as e:
        print(f'Warning: could not save Excel file ({e})')

    # Show first rows if summary not requested
    if not args.show_summary:
        print('\n' + '=' * 50)
        print('FIRST 10 ROWS')
        print('=' * 50)
        print(df.head(10))

    # Summaries use fixed prefix
    file_prefix = 'amr_data'
    create_summary(df, output_dir, file_prefix)


if __name__ == '__main__':
    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)],
                        format='%(levelname)-6s: "%(message)s" ( function=%(funcName)s() Line %(lineno)-4d)',
                        encoding='utf-8', level='INFO')
    main()
