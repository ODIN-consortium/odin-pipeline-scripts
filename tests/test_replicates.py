"""Tests for scripts/replicates.py: replicate pooling, as odin_pipeline does it.

The expectations mirror odin_pipeline's tests (backend/tests/test_replicates.py): the two code bases
must group, name and pool replicates identically, so that published results are reproducible
with either.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from replicates import (
    planned_inputs,
    plan_inputs,
    pooled_metadata_df,
    pooled_metadata_rows,
    replicate_groups,
    replicate_label,
    replicate_problems,
)


def _row(barcode, replicate=None, *, run="RUN1", code="AAAVRV_SG_G", date="20250326", protocol="P5",
         kit="RB_AMP", rtype=None):
    return {
        "run_accession": run, "barcode": barcode, "sample_code": code, "sampling_date": date,
        "protocol_id": protocol, "sequencing_kit_id": kit,
        "replicate": replicate, "replicate_type": rtype,
        "sample_id": f"{code}_{protocol}_{kit}", "alias": f"{code}_{barcode}",
    }


@pytest.mark.unit
def test_numbered_barcodes_form_one_pooled_group_in_replicate_order():
    groups = replicate_groups([_row("barcode17", "2"), _row("barcode14", "1")])
    assert len(groups) == 1
    assert groups[0].numbered
    assert groups[0].barcodes == ["barcode14", "barcode17"]
    assert groups[0].pooled_name == "barcode14-barcode17"


@pytest.mark.unit
def test_pooled_name_has_no_underscore():
    # the post-processing keys a report on the text before its first underscore
    assert "_" not in replicate_groups([_row("barcode01", "1"), _row("barcode02", "2")])[0].pooled_name


@pytest.mark.unit
def test_a_single_barcode_is_never_a_problem_whatever_its_number():
    (group,) = replicate_groups([_row("barcode05", "2")])
    assert group.problem is None and not group.numbered


@pytest.mark.unit
@pytest.mark.parametrize(
    "numbers, kind",
    [((None, None), "unnumbered"), (("1", None), "partial"), (("1", "1"), "duplicate")],
)
def test_groups_that_cannot_be_pooled(numbers, kind):
    (group,) = replicate_groups([_row("barcode01", numbers[0]), _row("barcode02", numbers[1])])
    assert group.problem == kind
    assert group.describe_problem()
    with pytest.raises(ValueError, match="cannot be processed"):
        plan_inputs([group], pool=True)


@pytest.mark.unit
def test_nan_and_text_nan_read_as_unnumbered():
    (group,) = replicate_groups([_row("barcode01", float("nan")), _row("barcode02", "nan")])
    assert group.problem == "unnumbered"


@pytest.mark.unit
def test_two_library_preps_of_one_sample_are_two_groups():
    groups = replicate_groups([_row("barcode01", protocol="P1"), _row("barcode02", protocol="P2")])
    assert len(groups) == 2 and all(g.problem is None for g in groups)


@pytest.mark.unit
def test_same_sample_in_two_runs_is_not_a_group_per_run():
    rows = [_row("barcode01", run="RUN1"), _row("barcode02", run="RUN2")]
    assert replicate_problems(rows) == []  # per accession: one barcode each
    assert [g.barcodes for g in replicate_groups(rows, by_run=False)] == [["barcode01", "barcode02"]]


@pytest.mark.unit
def test_merged_set_check_is_opt_in():
    rows = [_row("barcode01", run="RUN1"), _row("barcode02", run="RUN2")]
    assert replicate_problems(rows, merged_set=True)  # unnumbered once the two runs are one set
    assert replicate_problems(rows) == []


@pytest.mark.unit
def test_barcode_numbered_differently_across_merged_runs_is_inconsistent():
    rows = [_row("barcode01", "1", run="RUN1"), _row("barcode01", "2", run="RUN2"), _row("barcode02", "2", run="RUN1"),
            _row("barcode02", "1", run="RUN2")]
    (group,) = replicate_groups(rows, by_run=False)
    assert group.problem == "inconsistent"


@pytest.mark.unit
def test_barcode_in_two_merged_runs_is_one_member():
    rows = [_row("barcode01", "1", run="RUN1"), _row("barcode01", "1", run="RUN2"), _row("barcode02", "2", run="RUN1"),
            _row("barcode02", "2", run="RUN2")]
    assert planned_inputs(rows) == {"barcode01-barcode02": ["barcode01", "barcode02"]}


@pytest.mark.unit
def test_planned_inputs_pools_or_keeps_barcodes():
    rows = [_row("barcode14", "1"), _row("barcode17", "2"), _row("barcode05", code="OTHER_RW")]
    assert planned_inputs(rows) == {"barcode14-barcode17": ["barcode14", "barcode17"], "barcode05": ["barcode05"]}
    assert planned_inputs(rows, pool=False) == {
        "barcode14": ["barcode14"], "barcode17": ["barcode17"], "barcode05": ["barcode05"]}


@pytest.mark.unit
def test_a_row_the_grouping_leaves_out_is_still_an_input():
    rows = [{"run_accession": "RUN1", "barcode": "barcode09", "sample_code": "", "sample_id": "", "sampling_date": ""}]
    assert planned_inputs(rows) == {"barcode09": ["barcode09"]}


@pytest.mark.unit
def test_a_row_without_sample_code_groups_on_sample_id():
    rows = [{"run_accession": "R", "barcode": b, "sample_id": "S_P1_K", "sampling_date": "20250101", "replicate": n}
            for b, n in (("barcode01", "1"), ("barcode02", "2"))]
    assert planned_inputs(rows) == {"barcode01-barcode02": ["barcode01", "barcode02"]}


@pytest.mark.unit
def test_pooled_metadata_row_is_the_first_member_with_the_pool_named():
    rows = [_row("barcode17", "2", rtype="biological"), _row("barcode14", "1", rtype="biological"),
            _row("barcode05", code="OTHER_RW")]
    out = pooled_metadata_rows(rows)
    assert [r["barcode"] for r in out] == ["barcode14-barcode17", "barcode05"]
    pooled = out[0]
    assert pooled["replicate"] == "pooled"
    assert pooled["replicate_type"] == "biological"
    assert pooled["alias"] == "AAAVRV_SG_G_barcode14-barcode17"
    assert out[1]["replicate"] is None  # outside a group: unchanged


@pytest.mark.unit
def test_a_lone_numbered_barcode_keeps_its_number():
    (row,) = pooled_metadata_rows([_row("barcode05", "2")])
    assert row["barcode"] == "barcode05" and row["replicate"] == "2"


@pytest.mark.unit
def test_pooling_is_per_accession_so_a_merged_set_gives_one_pooled_row_per_run():
    rows = [_row("barcode01", "1", run="RUN1"), _row("barcode02", "2", run="RUN1"),
            _row("barcode01", "1", run="RUN2"), _row("barcode02", "2", run="RUN2")]
    out = pooled_metadata_rows(rows)
    assert [(r["run_accession"], r["barcode"]) for r in out] == [("RUN1", "barcode01-barcode02"),
                                                                  ("RUN2", "barcode01-barcode02")]


@pytest.mark.unit
def test_pooled_metadata_df_adds_the_replicate_columns_and_pools():
    df = pd.DataFrame([_row("barcode14", "1"), _row("barcode17", "2")]).drop(columns=["replicate_type"])
    out = pooled_metadata_df(df)
    assert list(out["barcode"]) == ["barcode14-barcode17"]
    assert list(out["replicate"]) == ["pooled"] and "replicate_type" in out.columns
    unpooled = pooled_metadata_df(df, pool=False)
    assert list(unpooled["barcode"]) == ["barcode14", "barcode17"]


@pytest.mark.unit
def test_replicate_label_is_text_for_a_number_or_pooled():
    assert replicate_label(None) == "" and replicate_label(float("nan")) == "" and replicate_label("") == ""
    assert replicate_label("1") == "1" and replicate_label("2.0") == "2" and replicate_label(3) == "3"
    assert replicate_label("pooled") == "pooled"
