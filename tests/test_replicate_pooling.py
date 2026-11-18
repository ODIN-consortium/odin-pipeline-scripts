"""End-to-end tests of replicate pooling and of sample_type / site from the samples sheet.

A small synthetic workbook stands in for the metadata workbook. The behaviour pinned here is what
odin_pipeline does with the same metadata, so that results from ``pipeline_scripts`` and from the
application agree:

- barcodes numbered as replicates of one sample are concatenated into one input named after them,
  classified once, and read back under one row whose ``replicate`` is ``pooled``;
- ``sample_type`` and ``sampling_site_id`` come from the samples sheet: ``SG_G`` stays whole and a
  site ID with an underscore (``DVDVRV_N``) is not cut short.
"""
import gzip
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from concatenate_fastq_by_sample import concatenate_fastq_files_by_metadata, get_metadata_info
from create_all_samples_csv import get_barcodes_from_metadata
from create_kraken_datasets import create_kraken_dataset_from_metadata
from nanopore_metadata import load_sample_lookup, site_and_type
from parse_amr_json import create_amr_dataframe_from_metadata
from replicates import planned_inputs

RUN = "20250326_1000_MN00001_FBD00001_aaaaaaaa"

NANOPORE_COLUMNS = ["sample_code", "sampling_date", "protocol_id", "sequencing_kit_id", "barcode", "sample_id",
                    "alias", "type", "runName", "sampleName", "run_accession", "replicate", "Notes"]


def _nanopore_row(code, barcode, replicate=None, date="20250326"):
    return [code, date, "P5", "RB_AMP", barcode, f"{code}_P5_RB_AMP", f"{code}_{barcode}", "test_sample",
            "runA", "sampleA", RUN, replicate, None]


def _write_workbook(path: Path, nanopore_rows):
    """The metadata workbook layout: nanopore header on row 2 and row 3 skipped; the other sheets
    have the header on row 1 and row 2 skipped."""
    def sheet(columns, rows, header_row, writer, name):
        descriptor = ["description"] * len(columns)
        frame = pd.DataFrame([descriptor] + rows, columns=columns)
        frame.to_excel(writer, sheet_name=name, index=False, startrow=header_row)

    with pd.ExcelWriter(path) as writer:
        sheet(["site_ID", "country", "longitude", "latitude"],
              [["AAAVRV", "Alphaland", 32.58, 0.32],
               ["DVDVRV_N", "Demoville", 10.75, 59.91]], 0, writer, "sites")
        sheet(["site_ID", "sample_type", "sample_code", "sampling_date", "partner_sample_code"],
              [["AAAVRV", "SG_G", "AAAVRV_SG_G", "20250326", "P-1"],
               ["DVDVRV_N", "RW", "DVDVRV_N_RW", "20250326", "P-2"]], 0, writer, "samples")
        sheet(NANOPORE_COLUMNS, nanopore_rows, 1, writer, "nanopore")


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "metadata.xlsx"
    _write_workbook(path, [
        _nanopore_row("AAAVRV_SG_G", "barcode14", "1"),
        _nanopore_row("AAAVRV_SG_G", "barcode17", "2"),
        _nanopore_row("DVDVRV_N_RW", "barcode05"),
    ])
    return str(path)


def _amr_json(path: Path, barcode: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({barcode: {"pass": True, "results": {"geneX": {"count": 1, "meta": [
        {"RESISTANCE": "ampicillin", "SEQUENCE": "ACGT", "START": 1, "END": 4, "%COVERAGE": 99.0,
         "%IDENTITY": 98.0}]}}}}))


def _kraken_report(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" 50.00\t500\t500\tU\t0\tunclassified\n 50.00\t500\t2\tR\t1\troot\n"
                    " 49.80\t498\t498\tD\t2\t  Bacteria\n")


def _amr_outputs(tmp_path, names):
    base = tmp_path / "data" / "nanopore_processed" / "outputs_wf_metagenomics_amr" / RUN
    for name in names:
        _amr_json(base / "amr" / f"{name}.amr.json", name)
        _kraken_report(base / "kraken2" / f"{name}.kraken2.report.txt")
    return str(tmp_path / "data")


class TestSiteAndTypeFromTheSamplesSheet:
    @pytest.mark.unit
    def test_lookup_keeps_a_two_part_type_and_an_underscore_in_the_site(self, workbook):
        lookup = load_sample_lookup(workbook)
        assert lookup["AAAVRV_SG_G"] == ("AAAVRV", "SG_G")
        assert lookup["DVDVRV_N_RW"] == ("DVDVRV_N", "RW")

    @pytest.mark.unit
    def test_the_old_parse_of_sample_id_gets_both_wrong(self):
        from nanopore_metadata import extract_site_and_type_from_sample_id
        assert extract_site_and_type_from_sample_id("AAAVRV_SG_G_P5_RB_AMP") == ("AAAVRV", "SG")
        assert extract_site_and_type_from_sample_id("DVDVRV_N_RW_P1_RB_AMP") == ("DVDVRV", "N")

    @pytest.mark.unit
    def test_site_and_type_uses_the_lookup_and_falls_back_to_sample_id(self, workbook, caplog):
        lookup = load_sample_lookup(workbook)
        assert site_and_type("AAAVRV_SG_G", "AAAVRV_SG_G_P5_RB_AMP", lookup) == ("AAAVRV", "SG_G")
        with caplog.at_level("WARNING"):
            assert site_and_type("NOPE_WW", "NOPE_WW_P1_RB_AMP", lookup) == ("NOPE", "WW")
        assert "not found in the samples sheet" in caplog.text
        assert site_and_type(float("nan"), "ABC_WW_P1_RB_AMP", None) == ("ABC", "WW")


class TestFastqPooling:
    @staticmethod
    def _fastq_pass(tmp_path):
        fastq_pass = tmp_path / "minknow" / "runA" / "sampleA" / RUN / "fastq_pass"
        payload = {}
        for barcode, data in (("barcode14", b"@r1\nAAAA\n+\n!!!!\n"), ("barcode17", b"@r2\nCCCC\n+\n####\n"),
                              ("barcode05", b"@r3\nGGGG\n+\n$$$$\n")):
            (fastq_pass / barcode).mkdir(parents=True)
            with gzip.open(fastq_pass / barcode / "part0.fastq.gz", "wb") as fh:
                fh.write(data)
            payload[barcode] = data
        return fastq_pass, payload

    @pytest.mark.unit
    def test_replicates_become_one_input_named_after_them(self, workbook, tmp_path):
        fastq_pass, payload = self._fastq_pass(tmp_path)
        run_accessions, barcode_metadata, _ = get_metadata_info(workbook, RUN, "run_accession")
        rows = [row for info in barcode_metadata.values() for row in info["rows"]]
        inputs = planned_inputs(rows)
        assert inputs == {"barcode14-barcode17": ["barcode14", "barcode17"], "barcode05": ["barcode05"]}

        out_dir = tmp_path / "tmp"
        outputs, identifier = concatenate_fastq_files_by_metadata(
            {RUN: fastq_pass}, barcode_metadata, str(out_dir), inputs)

        assert set(outputs) == {"barcode14-barcode17", "barcode05"}
        pooled = Path(outputs["barcode14-barcode17"])
        # wf-metagenomics wants one sub-directory per sample, and create_all_samples_csv.py reads the
        # sample name before the first underscore
        assert pooled.parent.name == "barcode14-barcode17"
        assert pooled.name == f"barcode14-barcode17_{identifier}.fastq.gz"
        with gzip.open(pooled, "rb") as fh:
            assert fh.read() == payload["barcode14"] + payload["barcode17"]
        with gzip.open(outputs["barcode05"], "rb") as fh:
            assert fh.read() == payload["barcode05"]

    @pytest.mark.unit
    def test_without_pooling_every_barcode_is_its_own_input(self, workbook, tmp_path):
        fastq_pass, _ = self._fastq_pass(tmp_path)
        _, barcode_metadata, _ = get_metadata_info(workbook, RUN, "run_accession")
        rows = [row for info in barcode_metadata.values() for row in info["rows"]]
        outputs, _ = concatenate_fastq_files_by_metadata(
            {RUN: fastq_pass}, barcode_metadata, str(tmp_path / "tmp"), planned_inputs(rows, pool=False))
        assert set(outputs) == {"barcode14", "barcode17", "barcode05"}

    @pytest.mark.unit
    def test_default_inputs_are_one_per_barcode(self, workbook, tmp_path):
        fastq_pass, _ = self._fastq_pass(tmp_path)
        _, barcode_metadata, _ = get_metadata_info(workbook, RUN, "run_accession")
        outputs, _ = concatenate_fastq_files_by_metadata({RUN: fastq_pass}, barcode_metadata, str(tmp_path / "tmp"))
        assert set(outputs) == {"barcode14", "barcode17", "barcode05"}

    @pytest.mark.unit
    def test_taxprofiler_samplesheet_names_the_pooled_input(self, workbook):
        assert get_barcodes_from_metadata(workbook, RUN, "run_accession") == ["barcode14-barcode17", "barcode05"]


class TestAmrDataset:
    @pytest.mark.unit
    def test_pooled_input_is_one_row_with_replicate_pooled(self, workbook, tmp_path):
        data = _amr_outputs(tmp_path, ["barcode14-barcode17", "barcode05"])
        df, _ = create_amr_dataframe_from_metadata(workbook, data)

        assert set(df["barcode"]) == {"barcode14-barcode17", "barcode05"}
        by_barcode = df.drop_duplicates("barcode").set_index("barcode")
        assert by_barcode.loc["barcode14-barcode17", "replicate"] == "pooled"
        assert by_barcode.loc["barcode05", "replicate"] == ""
        assert by_barcode.loc["barcode14-barcode17", "alias"] == "AAAVRV_SG_G_barcode14-barcode17"

    @pytest.mark.unit
    def test_sample_type_and_site_come_from_the_samples_sheet(self, workbook, tmp_path):
        data = _amr_outputs(tmp_path, ["barcode14-barcode17", "barcode05"])
        df, _ = create_amr_dataframe_from_metadata(workbook, data)

        by_barcode = df.drop_duplicates("barcode").set_index("barcode")
        assert by_barcode.loc["barcode14-barcode17", "sample_type"] == "SG_G"
        assert by_barcode.loc["barcode14-barcode17", "sampling_site_id"] == "AAAVRV"
        assert by_barcode.loc["barcode14-barcode17", "country"] == "Alphaland"
        assert by_barcode.loc["barcode05", "sample_type"] == "RW"
        assert by_barcode.loc["barcode05", "sampling_site_id"] == "DVDVRV_N"
        assert by_barcode.loc["barcode05", "country"] == "Demoville"

    @pytest.mark.unit
    def test_per_barcode_keeps_each_member_and_its_number(self, workbook, tmp_path):
        data = _amr_outputs(tmp_path, ["barcode14", "barcode17", "barcode05"])
        df, _ = create_amr_dataframe_from_metadata(workbook, data, pool_replicates=False)

        by_barcode = df.drop_duplicates("barcode").set_index("barcode")
        assert set(by_barcode.index) == {"barcode14", "barcode17", "barcode05"}
        assert by_barcode.loc["barcode14", "replicate"] == "1"
        assert by_barcode.loc["barcode17", "replicate"] == "2"
        assert by_barcode.loc["barcode05", "replicate"] == ""

    @pytest.mark.unit
    def test_unnumbered_group_is_refused(self, tmp_path):
        path = tmp_path / "bad.xlsx"
        _write_workbook(path, [_nanopore_row("AAAVRV_SG_G", "barcode14"), _nanopore_row("AAAVRV_SG_G", "barcode17")])
        data = _amr_outputs(tmp_path, ["barcode14", "barcode17"])
        with pytest.raises(ValueError, match="cannot be pooled"):
            create_amr_dataframe_from_metadata(str(path), data)

    @pytest.mark.unit
    def test_a_merged_set_is_read_once_not_once_per_accession(self, tmp_path):
        """Two loadings of one flow cell are one output but two metadata rows (which may differ in
        type or runName). The sample's genes must be counted once, as odin_pipeline does."""
        run2 = "20250327_0900_MN00001_FBD00001_bbbbbbbb"
        first = _nanopore_row("AAAVRV_SG_G", "barcode05")
        second = _nanopore_row("AAAVRV_SG_G", "barcode05")
        second[7], second[8], second[10] = None, "runB", run2   # type, runName, run_accession
        path = tmp_path / "merged.xlsx"
        _write_workbook(path, [first, second])
        out = tmp_path / "data" / "nanopore_processed" / "outputs_wf_metagenomics_amr" / "sampleA"
        _amr_json(out / "amr" / "barcode05.amr.json", "barcode05")
        _kraken_report(out / "kraken2" / "barcode05.kraken2.report.txt")

        df, processed = create_amr_dataframe_from_metadata(str(path), str(tmp_path / "data"))

        assert len(df) == 1, "the merged set's one JSON gave a row per accession"
        assert processed == {RUN, run2}


class TestKrakenDataset:
    COLUMNS = ['Pct. of Frags', 'No of Frags root', 'No of Frags', 'Rank code', 'NCBI tax ID', 'Scientific name']

    @pytest.mark.unit
    def test_pooled_report_is_read_once_with_replicate_pooled(self, workbook, tmp_path):
        base = tmp_path / "data" / "nanopore_processed" / "outputs_taxprofiler" / RUN / "kraken2" / "db6"
        for name in ("barcode14-barcode17", "barcode05"):
            _kraken_report(base / f"{name}_db6.kraken2.report.txt")

        df, _ = create_kraken_dataset_from_metadata(workbook, str(tmp_path / "data"), self.COLUMNS)

        assert set(df["barcode"]) == {"barcode14-barcode17", "barcode05"}
        by_barcode = df.drop_duplicates("barcode").set_index("barcode")
        assert by_barcode.loc["barcode14-barcode17", "replicate"] == "pooled"
        assert by_barcode.loc["barcode14-barcode17", "sample_type"] == "SG_G"
        assert by_barcode.loc["barcode05", "sampling_site_id"] == "DVDVRV_N"

    @pytest.mark.unit
    def test_a_member_barcode_does_not_pick_up_the_pooled_report(self, workbook, tmp_path):
        """'barcode14' must not match 'barcode14-barcode17_db6.kraken2.report.txt'."""
        from create_kraken_datasets import create_kraken_dataset
        base = tmp_path / "kraken2" / "db6"
        _kraken_report(base / "barcode14-barcode17_db6.kraken2.report.txt")
        assert create_kraken_dataset(str(tmp_path), self.COLUMNS, prefix="barcode14").empty
        assert not create_kraken_dataset(str(tmp_path), self.COLUMNS, prefix="barcode14-barcode17").empty
