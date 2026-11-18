#!/usr/bin/env python3
"""Which local Kraken2 database, and taxonomy, an AMR run gives to wf-metagenomics.

The AMR genes come from abricate against the AMR database (CARD); the Kraken2 step only
gives the per-barcode read totals in amr_data.feather. Using the database taxprofiler uses
makes those totals comparable with the taxonomy datasets.

Which database:
  - setting 'download'  : none; wf-metagenomics downloads the --database_set.
  - setting a directory : that one.
  - setting empty       : the kraken2 row of databases.csv whose directory holds a Bracken
                          file; none (download) when no row does.

wf-metagenomics refuses a database directory without a Bracken ``database*mers.kmer_distrib``
file, so that file is what makes a database usable here. The taxonomy is the build's own
``taxonomy/`` subdirectory when it has names.dmp and nodes.dmp; otherwise wf-metagenomics
fetches one.

Usage (prints the database directory on line 1 and the taxonomy on line 2, either may be empty):
    amr_kraken2_db.py [--setting VALUE] [--databases-csv FILE]
"""
import argparse
import csv
import sys
from pathlib import Path

DOWNLOAD = "download"
BRACKEN_GLOB = "database*mers.kmer_distrib"


def _has_bracken(path: Path) -> bool:
    return path.is_dir() and any(path.glob(BRACKEN_GLOB))


def _kraken2_dirs(databases_csv: str) -> list:
    """Directories of the kraken2 rows of databases.csv that exist and hold a Bracken file."""
    found = []
    with open(databases_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if (row.get("tool") or "").strip() != "kraken2":
                continue
            path = Path((row.get("db_path") or "").strip())
            if _has_bracken(path) and path not in found:
                found.append(path)
    return found


def resolve(setting: str = "", databases_csv: str = "") -> tuple:
    """(database directory, taxonomy directory) for an AMR run; empty strings for none.

    Raises ValueError when the database cannot be used, so the run fails before any FASTQ
    is concatenated rather than after.
    """
    setting = (setting or "").strip()
    if setting.lower() == DOWNLOAD:
        return "", ""
    if setting:
        local = Path(setting)
        if not local.is_dir():
            raise ValueError(f"AMR Kraken2 database directory not found: {setting}")
        if not any(local.glob(BRACKEN_GLOB)):
            raise ValueError(
                f"AMR Kraken2 database {setting} has no Bracken file "
                "(database<length>mers.kmer_distrib); wf-metagenomics will not use it without one."
            )
    else:
        if not databases_csv or not Path(databases_csv).is_file():
            return "", ""
        candidates = _kraken2_dirs(databases_csv)
        if not candidates:
            return "", ""
        if len(candidates) > 1:
            raise ValueError(
                "More than one Kraken2 database in databases.csv has a Bracken file ("
                + ", ".join(str(c) for c in candidates)
                + "); name the one AMR runs should use with --database or kraken2_db_amr."
            )
        local = candidates[0]

    taxonomy = local / "taxonomy"
    has_taxonomy = all((taxonomy / name).is_file() for name in ("names.dmp", "nodes.dmp"))
    return str(local), str(taxonomy) if has_taxonomy else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--setting", default="", help="a directory, 'download', or empty to use databases.csv")
    ap.add_argument("--databases-csv", default="", help="databases.csv of the taxprofiler run")
    args = ap.parse_args(argv)
    try:
        db, taxonomy = resolve(args.setting, args.databases_csv)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(db)
    print(taxonomy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
