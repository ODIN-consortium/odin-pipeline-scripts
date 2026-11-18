"""Replicate groups: which barcodes of a run carry the same sample, and what that means.

A port of ``odin_pipeline/backend/app/pipeline/replicates.py``, so that ``pipeline_scripts`` pools
replicates exactly as the web application does and the two give the same results. Keep the two
files in step: the grouping rule, the pooled name, the problem checks and the pooled metadata row
are the same.

A sampling occasion normally has one barcode in a run. When it has several, the ``replicate``
column of the metadata's ``nanopore`` sheet says why: numbered barcodes are replicates of one
sample and are pooled before classification; unnumbered ones are a metadata error (two samples
sharing a label, a mistyped date) until someone says otherwise.

The group key is the sample within the run: ``sample_code``, ``sampling_date``, ``protocol_id``
and ``sequencing_kit_id``. Two library preps of one sample (different protocol or kit) are two
groups, as they are two ``sample_id`` values.

Where it is used:

- ``concatenate_fastq_by_sample.py`` concatenates a group's reads into one input named after
  its barcodes, so the workflow classifies the sample once;
- ``create_kraken_datasets.py`` and ``parse_amr_json.py`` attach the sample's metadata to that
  pooled input (``pooled_metadata_df``), with ``replicate`` set to ``pooled``;
- ``create_all_samples_csv.py`` names the pooled input in the taxprofiler samplesheet.

Pooling is the default for every pipeline, as in the application. AMR can be switched back to
one input per barcode (``amr_replicates = per_barcode``); the application's default is pooled.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

# The ``replicate`` value of a dataset row built from a replicate group's pooled reads. The
# row's ``barcode`` then names the members.
POOLED = "pooled"

# Joins the member barcodes into the pooled input's name. The name becomes a directory under
# wf-metagenomics' ``--fastq``, the ``sample`` of a taxprofiler samplesheet row and the prefix
# of the reports both workflows write, so it must be safe in a path and in a shell, and must
# contain no underscore: the post-processing keys reports on the text before the first one.
POOL_SEPARATOR = "-"

#: The two values of the AMR ``amr_replicates`` setting.
AMR_REPLICATES_POOL = "pool"
AMR_REPLICATES_PER_BARCODE = "per_barcode"


@dataclass(frozen=True)
class Member:
    barcode: str
    replicate: int | None
    replicate_type: str | None


@dataclass(frozen=True)
class ReplicateGroup:
    """The barcodes of one sample within one run, or within one merged run set."""

    run_accession: str | None  # None when the group spans a merged run set
    sample_code: str
    sampling_date: str
    protocol_id: str | None
    sequencing_kit_id: str | None
    members: tuple[Member, ...]  # numbered members first, by number; then by barcode
    # Barcodes that carry different replicate numbers in different accessions of a merged run
    # set. Always empty for a group built within one accession.
    inconsistent: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.sample_code} ({self.sampling_date})"

    @property
    def barcodes(self) -> list[str]:
        return [m.barcode for m in self.members]

    @property
    def numbered(self) -> bool:
        """Several barcodes, every one numbered, no number used twice: pooled as one."""
        return len(self.members) > 1 and self.problem is None

    @property
    def problem(self) -> str | None:
        """Why the group can be neither pooled nor passed through, or None.

        A single barcode is never a problem, whatever its number: its partner may have been
        left out, and a group of one is just a barcode.
        """
        if self.inconsistent:
            return "inconsistent"
        if len(self.members) < 2:
            return None
        numbers = [m.replicate for m in self.members if m.replicate is not None]
        if not numbers:
            return "unnumbered"
        if len(numbers) < len(self.members):
            return "partial"
        if len(set(numbers)) < len(numbers):
            return "duplicate"
        return None

    @property
    def pooled_name(self) -> str:
        """The name of the pooled input: the member barcodes in replicate order."""
        return POOL_SEPARATOR.join(self.barcodes)

    @property
    def replicate_type(self) -> str:
        """The members' types, ';'-joined when they differ; '' when none is set."""
        return ";".join(sorted({m.replicate_type for m in self.members if m.replicate_type}))

    def describe_problem(self) -> str:
        """The operator-facing sentence for ``problem``; '' when there is none."""
        kind = self.problem
        if kind is None:
            return ""
        where = f"in run {self.run_accession}" if self.run_accession else "in the merged runs"
        prep = ""
        if self.protocol_id or self.sequencing_kit_id:
            prep = " for" + (f" protocol {self.protocol_id}" if self.protocol_id else "") + (
                f" kit {self.sequencing_kit_id}" if self.sequencing_kit_id else ""
            )
        if kind == "unnumbered":
            return (
                f"Sample {self.label}: barcodes {', '.join(self.barcodes)} are linked {where}"
                f"{prep}. If they are replicates of one sample, give each a replicate number "
                f"(1, 2, ...) in the 'replicate' column of the nanopore sheet and they will be "
                f"pooled; otherwise correct the sample or the date on the barcode that is wrong."
            )
        if kind == "partial":
            numbered = [m.barcode for m in self.members if m.replicate is not None]
            unnumbered = [m.barcode for m in self.members if m.replicate is None]
            return (
                f"Sample {self.label}: replicate numbers on {', '.join(numbered)} but not on "
                f"{', '.join(unnumbered)} {where}. Number every barcode of the group, or none."
            )
        if kind == "duplicate":
            by_number: dict[int, list[str]] = defaultdict(list)
            for m in self.members:
                if m.replicate is not None:
                    by_number[m.replicate].append(m.barcode)
            repeated = "; ".join(
                f"replicate {n} on {', '.join(bcs)}"
                for n, bcs in sorted(by_number.items())
                if len(bcs) > 1
            )
            return (
                f"Sample {self.label}: {repeated} {where}. Replicate numbers within a group "
                f"must be distinct."
            )
        return (
            f"Sample {self.label}: {', '.join(self.inconsistent)} carry different replicate "
            f"numbers in the runs being merged. Give each barcode the same number in every "
            f"accession of the run."
        )

    def describe_pooling(self) -> str:
        """The note shown for a group that will be pooled."""
        return (
            f"{self.label}: replicates {', '.join(self.barcodes)} will be pooled before "
            f"classification."
        )


def _text(value: Any) -> str:
    """A cell as stripped text: '' for None, NaN and the string 'nan'."""
    if value is None:
        return ""
    try:
        if value != value:  # NaN
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _number(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    return int(float(text))


def _row_value(row: Mapping[str, Any], key: str) -> str:
    return _text(row.get(key))


def replicate_groups(rows: Iterable[Mapping[str, Any]], *, by_run: bool = True) -> list[ReplicateGroup]:
    """Group barcode rows by the sample they carry.

    ``rows`` are mappings with ``run_accession``, ``barcode``, ``sample_code``,
    ``sampling_date``, ``protocol_id``, ``sequencing_kit_id``, ``replicate`` and
    ``replicate_type`` -- the columns of the ``nanopore`` sheet. Missing keys read as empty,
    and a row without ``sample_code`` falls back to its ``sample_id``. Rows without a barcode,
    a sample code or a date are left out: an unlinked barcode is a different error, reported
    elsewhere.

    With ``by_run`` the key includes the accession, which is the unit the replicate numbers are
    entered and validated in. Without it the rows of a merged run set (continuations of one
    flow cell) fold into one group per sample, a barcode being one member however many
    accessions it appears in; a barcode numbered differently across them makes the group
    ``inconsistent``.

    Groups come back in first-seen order, one per sample, singletons included.
    """
    keyed: dict[tuple, dict[str, dict[str, Any]]] = {}
    for row in rows:
        barcode = _row_value(row, "barcode")
        sample_code = _row_value(row, "sample_code") or _row_value(row, "sample_id")
        sampling_date = _row_value(row, "sampling_date")
        if not barcode or not sample_code or not sampling_date:
            continue
        key = (
            _row_value(row, "run_accession") if by_run else None,
            sample_code,
            sampling_date,
            _row_value(row, "protocol_id") or None,
            _row_value(row, "sequencing_kit_id") or None,
        )
        members = keyed.setdefault(key, {})
        entry = members.setdefault(barcode, {"numbers": set(), "types": set()})
        entry["numbers"].add(_number(row.get("replicate")))
        replicate_type = _row_value(row, "replicate_type")
        if replicate_type:
            entry["types"].add(replicate_type)

    groups: list[ReplicateGroup] = []
    for (run_accession, sample_code, sampling_date, protocol_id, kit), members in keyed.items():
        inconsistent: list[str] = []
        built: list[Member] = []
        for barcode, entry in members.items():
            numbers = entry["numbers"]
            if len(numbers) > 1:
                inconsistent.append(barcode)
            built.append(
                Member(
                    barcode,
                    next(iter(numbers)) if len(numbers) == 1 else None,
                    ";".join(sorted(entry["types"])) or None,
                )
            )
        built.sort(key=lambda m: (m.replicate is None, m.replicate or 0, m.barcode))
        groups.append(
            ReplicateGroup(
                run_accession or None,
                sample_code,
                sampling_date,
                protocol_id,
                kit,
                tuple(built),
                tuple(sorted(inconsistent)),
            )
        )
    return groups


def plan_inputs(groups: Iterable[ReplicateGroup], *, pool: bool) -> dict[str, list[str]]:
    """Map each input name to the barcodes concatenated into it.

    With ``pool`` every numbered group becomes one input under its pooled name; every other
    barcode is an input of its own. Without it each barcode is its own input. Raises
    ``ValueError`` on a group with a problem, naming it, because the check before the run
    should have refused it and silently processing it would hide the error.
    """
    inputs: dict[str, list[str]] = {}
    for group in groups:
        if group.problem is not None:
            raise ValueError(f"Replicate group cannot be processed. {group.describe_problem()}")
        if pool and group.numbered:
            inputs[group.pooled_name] = group.barcodes
        else:
            for barcode in group.barcodes:
                inputs[barcode] = [barcode]
    return inputs


def replicate_problems(rows: Iterable[Mapping[str, Any]], *, merged_set: bool = False) -> list[str]:
    """The operator-facing sentences for every replicate group that cannot be processed.

    Run before any work is done. Each accession is checked by itself, which is the unit the
    replicate numbers are entered in. With ``merged_set`` the rows are the runs processed
    together (continuations of one flow cell) and the merged set is checked as well, because
    the FASTQ files are pooled across it. Pass it only for such a set: over a whole workbook
    it would fold every repeat of a sample on another flow cell into one group.
    """
    rows = [dict(r) for r in rows]
    errors: list[str] = []
    accessions = list(dict.fromkeys(_row_value(r, "run_accession") for r in rows))
    for group in replicate_groups(rows, by_run=True):
        if group.problem is not None:
            errors.append(group.describe_problem())
    if merged_set and len(accessions) > 1 and not errors:
        for group in replicate_groups(rows, by_run=False):
            if group.problem is not None:
                errors.append(group.describe_problem())
    return errors


def pooled_metadata_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The metadata rows a dataset builder should attach when replicate groups were pooled.

    Takes the per-barcode rows of the ``nanopore`` sheet and replaces each numbered group's
    rows with one row for the pooled input: the first member's row, with ``barcode`` and
    ``alias`` naming the pool, ``replicate`` set to ``"pooled"`` and ``replicate_type`` the
    members' types. Rows outside a numbered group pass through unchanged, so a lone numbered
    barcode keeps its number.

    Rows are grouped per accession, like the samplesheet that produced the output, and the
    result keeps the input's order with each pool at its first member's position.
    """
    rows = [dict(r) for r in rows]
    pools: dict[tuple[str, str], ReplicateGroup] = {}
    for group in replicate_groups(rows, by_run=True):
        if group.numbered:
            for barcode in group.barcodes:
                pools[(group.run_accession or "", barcode)] = group

    out: list[dict[str, Any]] = []
    written: set[tuple[str, str]] = set()
    for row in rows:
        group = pools.get((_row_value(row, "run_accession"), _row_value(row, "barcode")))
        if group is None:
            out.append(row)
            continue
        key = (group.run_accession or "", group.pooled_name)
        if key in written:
            continue
        written.add(key)
        pooled = dict(row)
        pooled["barcode"] = group.pooled_name
        pooled["alias"] = f"{group.sample_code}_{group.pooled_name}"
        pooled["replicate"] = POOLED
        pooled["replicate_type"] = group.replicate_type
        out.append(pooled)
    return out


def pooled_metadata_df(metadata_df: pd.DataFrame, *, pool: bool = True) -> pd.DataFrame:
    """``pooled_metadata_rows`` for a ``nanopore`` sheet DataFrame.

    Returns a frame with the same columns plus ``replicate`` and ``replicate_type`` (empty where
    the sheet has none), in which every numbered replicate group is one row. With ``pool`` False
    the rows are returned unchanged, apart from those two columns.
    """
    df = metadata_df.copy()
    for column in ("replicate", "replicate_type"):
        if column not in df.columns:
            df[column] = ""
    if not pool or df.empty:
        return df.reset_index(drop=True)
    rows = pooled_metadata_rows(df.to_dict("records"))
    return pd.DataFrame(rows, columns=list(df.columns)).reset_index(drop=True)


def planned_inputs(rows: Iterable[Mapping[str, Any]], *, pool: bool = True) -> dict[str, list[str]]:
    """Input name -> barcodes for the rows of a run set, pooled across the merged accessions.

    A barcode the grouping leaves out (no sample code, no date) is an input of its own, so
    nothing is dropped. Raises ``ValueError`` for a group that cannot be pooled.
    """
    rows = [dict(r) for r in rows]
    inputs = plan_inputs(replicate_groups(rows, by_run=False), pool=pool)
    planned = {barcode for barcodes in inputs.values() for barcode in barcodes}
    for row in rows:
        barcode = _row_value(row, "barcode")
        if barcode and barcode not in planned:
            inputs[barcode] = [barcode]
            planned.add(barcode)
    return inputs


def replicate_label(value: Any) -> str:
    """The dataset's text form of ``replicate``: '', a number, or ``pooled``.

    The datasets store it as text so that a pooled row and a numbered row fit one column.
    """
    text = _text(value)
    if not text or text == POOLED:
        return text
    return str(int(float(text)))
