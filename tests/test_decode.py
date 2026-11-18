"""
Tests for decode.py — grouping of Biomeme wells into samples.

A sample's ``Biomeme_sample_ID`` in the metadata is the comma-separated list of
well labels that belong to it in ONE run's Excel file. Labels (1..8, NTC..) are
reused in every run, so the lookup must be built per run. These tests build small
Biomeme-layout workbooks and call the real ``extract_edna``.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from decode import extract_edna  # noqa: E402

TARGET = 'Khe'      # present in config/assay-params.csv
FLUOR = 'red'


def write_run(path, run_name, wells):
    """Write a one-sheet workbook in the Biomeme Cq-export layout decode.py reads.

    wells: list of (well_number, label, cq). Row 7 = wells, 8 = fluorophore,
    10 = sample label, 11 = target, 12 = Cq; A12 == 'Cq' marks a Cq sheet.
    """
    wb = Workbook()
    ws = wb.active
    ws['B1'] = run_name
    ws['B2'] = '2025-09-11 09:09:38'
    ws['A12'] = 'Cq'
    for i, (well, label, cq) in enumerate(wells):
        col = 2 + i
        ws.cell(7, col, well)
        ws.cell(8, col, FLUOR)
        ws.cell(10, col, label)
        ws.cell(11, col, TARGET)
        ws.cell(12, col, cq)
    wb.save(path)
    return str(path)


def metadata(rows):
    """rows: list of (biomeme_run_name, Biomeme_sample_ID, sample_code)."""
    return pd.DataFrame(rows, columns=['biomeme_run_name', 'Biomeme_sample_ID', 'sample_code'])


def well(df, label):
    rows = df[df['Biomeme replicate'] == label]
    assert len(rows) == 1, f"expected one row for well {label!r}, got {len(rows)}"
    return rows.iloc[0]


# Run A: wells 5 and 6 are DIFFERENT samples; run B: wells 5 and 6 are ONE sample.
# Run B's metadata row comes last, which is what made the old global lookup merge
# run A's wells 5 and 6.
META = metadata([
    ('RUN_A', '5,NTC', 'S1'),
    ('RUN_A', '6,NTC', 'S2'),
    ('RUN_B', '5,6,NTC', 'S3'),
])
RUN_A_WELLS = [(5, '5', 0.0), (6, '6', 38.13), (9, 'NTC', 0.0)]
RUN_B_WELLS = [(5, '5', 30.0), (6, '6', 31.0), (9, 'NTC', 0.0)]


# Run N: the NTC amplifies at Cq 33. Well 1 amplified 5 cycles earlier (real signal),
# well 2 one cycle earlier (inside the 2-cycle margin), well 3 two cycles later (weaker
# than the blank). Each is its own single-well sample, so an untouched well is flag 2.
META_NTC = metadata([
    ('RUN_N', '1,NTC', 'S1'),
    ('RUN_N', '2,NTC', 'S2'),
    ('RUN_N', '3,NTC', 'S3'),
])
RUN_N_WELLS = [(1, '1', 28.0), (2, '2', 32.0), (3, '3', 35.0), (9, 'NTC', 33.0)]


class TestNtcRule:
    """A well counts only when it amplified at least NTC_MARGIN_CQ cycles earlier than the
    run's strongest amplifying NTC. Cq is inverse to abundance, so the direction matters:
    the untrustworthy wells are those at or above the NTC's Cq, not below it."""

    @pytest.mark.unit
    def test_well_well_before_the_ntc_is_kept(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'n.xlsx', 'RUN_N', RUN_N_WELLS), META_NTC)
        assert well(out, '1')['quality_flag'] == 2          # single well: questionable, not rejected
        assert well(out, '1')['presence'] == 'true_x'

    @pytest.mark.unit
    def test_well_within_the_margin_of_the_ntc_is_rejected(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'n.xlsx', 'RUN_N', RUN_N_WELLS), META_NTC)
        assert well(out, '2')['quality_flag'] == 4
        assert well(out, '2')['presence'] == 'false'

    @pytest.mark.unit
    def test_well_later_than_the_ntc_is_rejected(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'n.xlsx', 'RUN_N', RUN_N_WELLS), META_NTC)
        assert well(out, '3')['quality_flag'] == 4
        assert well(out, '3')['presence'] == 'false'
        # the NTC row (one per run) carries no presence
        assert out[out['Biomeme replicate'] == 'NTC']['presence'].isna().all()

    @pytest.mark.unit
    def test_non_amplifying_ntc_imposes_no_rule(self, tmp_path):
        wells = [(1, '1', 28.0), (2, '2', 32.0), (3, '3', 35.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'n.xlsx', 'RUN_N', wells), META_NTC)
        assert [well(out, w)['quality_flag'] for w in ('1', '2', '3')] == [2, 2, 2]

    @pytest.mark.unit
    def test_strongest_ntc_sets_the_floor(self, tmp_path):
        # Two NTCs at 33 and 37: the floor is 33, so a well at 34 (earlier than one NTC,
        # later than the other) is rejected.
        meta = metadata([('RUN_N', '1,NTC1,NTC2', 'S1'), ('RUN_N', '2,NTC1,NTC2', 'S2')])
        wells = [(1, '1', 30.0), (2, '2', 34.0), (9, 'NTC1', 37.0), (10, 'NTC2', 33.0)]
        out = extract_edna(write_run(tmp_path / 'n.xlsx', 'RUN_N', wells), meta)
        assert well(out, '1')['quality_flag'] == 2
        assert well(out, '2')['quality_flag'] == 4


class TestDilutionFactor:
    """The factor lives in the metadata, so it can only be applied after the merge — look
    for it earlier and it is never found, leaving 'Abundance diluted' equal to 'Abundance'.
    The factor is the fraction of original strength in the reaction, so the corrected
    abundance is Abundance / factor (a 1:2 dilution doubles the copies)."""

    @pytest.mark.unit
    def test_abundance_diluted_corrects_for_the_sample_dilution(self, tmp_path):
        meta = pd.DataFrame(
            [('RUN_D', '5,NTC', 'S1', 0.5), ('RUN_D', '6,NTC', 'S2', None)],
            columns=['biomeme_run_name', 'Biomeme_sample_ID', 'sample_code', 'dilution_factor'])
        wells = [(5, '5', 30.0), (6, '6', 31.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'd.xlsx', 'RUN_D', wells), meta)
        w5, w6 = well(out, '5'), well(out, '6')
        assert w5['Abundance diluted'] == pytest.approx(w5['Abundance'] / 0.5)
        assert w6['Abundance diluted'] == pytest.approx(w6['Abundance'])   # no factor: unchanged

    @pytest.mark.unit
    def test_without_a_dilution_column_diluted_equals_abundance(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        w = well(out, '5')
        assert w['Abundance diluted'] == pytest.approx(w['Abundance'])


class TestWellGroupingIsPerRun:

    @pytest.mark.unit
    def test_non_amplifying_well_does_not_inherit_neighbour_sample_mean(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'a.xlsx', 'RUN_A', RUN_A_WELLS), META)

        w5, w6 = well(out, '5'), well(out, '6')
        assert w5['sample_code'] == 'S1' and w6['sample_code'] == 'S2'
        assert pd.isna(w5['Mean Abundance'])
        assert w5['presence'] == 'false'
        assert w6['Mean Abundance'] == pytest.approx(w6['Abundance'])
        assert w6['quality_flag'] == 2 and w6['presence'] == 'true_x'

    @pytest.mark.unit
    def test_two_wells_of_one_sample_share_their_own_mean(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)

        w5, w6 = well(out, '5'), well(out, '6')
        expected = (w5['Abundance'] + w6['Abundance']) / 2
        assert w5['sample_code'] == 'S3' and w6['sample_code'] == 'S3'
        assert w5['Mean Abundance'] == pytest.approx(expected)
        assert w6['Mean Abundance'] == pytest.approx(expected)
        assert (w5['quality_flag'], w6['quality_flag']) == (1, 1)
        assert (w5['presence'], w6['presence']) == ('true', 'true')

    @pytest.mark.unit
    def test_well_listed_in_two_rows_of_same_run_raises(self, tmp_path):
        bad = metadata([('RUN_A', '5,NTC', 'S1'), ('RUN_A', '5,6,NTC', 'S2')])
        with pytest.raises(ValueError, match="well '5' is listed in two metadata rows"):
            extract_edna(write_run(tmp_path / 'a.xlsx', 'RUN_A', RUN_A_WELLS), bad)

    @pytest.mark.unit
    def test_same_label_in_different_runs_is_not_a_conflict(self, tmp_path):
        # META lists "5" for both RUN_A and RUN_B — legitimate, must not raise.
        extract_edna(write_run(tmp_path / 'a.xlsx', 'RUN_A', RUN_A_WELLS), META)
        extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)


class TestPositiveControl:

    @pytest.mark.unit
    def test_positive_control_is_shared_and_never_a_replicate(self, tmp_path):
        """Every sample row lists the run's POS well; it is not a conflict, not a replicate
        and not part of any sample's mean, and a well labelled 'Pos' by the device is the same."""
        meta = metadata([('RUN_D', '1,2,POS,NTC', 'S5'), ('RUN_D', '3,POS,NTC', 'S6')])
        wells = [(1, '1', 30.0), (2, '2', 31.0), (3, '3', 32.0), (8, 'Pos', 20.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'd.xlsx', 'RUN_D', wells), meta)

        w1, w2, w3 = well(out, '1'), well(out, '2'), well(out, '3')
        assert w1['Mean Abundance'] == pytest.approx((w1['Abundance'] + w2['Abundance']) / 2)
        assert w3['Mean Abundance'] == pytest.approx(w3['Abundance'])
        assert w3['quality_flag'] == 2          # one replicate, not two — POS does not count


class TestMeanAbundanceExcludesNtc:

    @pytest.mark.unit
    def test_amplifying_ntc_is_not_averaged_into_sample(self, tmp_path):
        meta = metadata([('RUN_C', '7,8,NTC', 'S4')])
        wells = [(7, '7', 30.0), (8, '8', 31.0), (9, 'NTC', 33.68)]
        out = extract_edna(write_run(tmp_path / 'c.xlsx', 'RUN_C', wells), meta)

        w7, w8 = well(out, '7'), well(out, '8')
        expected = (w7['Abundance'] + w8['Abundance']) / 2
        assert w7['Mean Abundance'] == pytest.approx(expected)
        assert w8['Mean Abundance'] == pytest.approx(expected)
        assert pd.isna(well(out, 'NTC')['Mean Abundance'])

    @pytest.mark.unit
    def test_ntc_rows_carry_no_abundance_derived_values(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)

        ntc = well(out, 'NTC')
        for col in ('Abundance', 'Abundance diluted', 'Mean Abundance', 'log1pMeanAbundance'):
            assert pd.isna(ntc[col]), f"NTC row has {col} = {ntc[col]!r}"
        assert ntc['presence'] is None or pd.isna(ntc['presence'])


ABUNDANCE_COLUMNS = ('Abundance', 'Abundance diluted', 'Mean Abundance', 'log1pMeanAbundance')


class TestLog1pColumn:

    @pytest.mark.unit
    def test_log1p_mean_abundance_is_ln_of_mean_plus_one_and_named_so(self, tmp_path):
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        w = well(out, '5')
        assert 'logMeanAbundance' not in out.columns        # the log10-looking name is gone
        assert w['log1pMeanAbundance'] == pytest.approx(np.log1p(w['Mean Abundance']))


class TestControlWellRows:
    """One row per physical control well per run.

    Copying a control once per sample that lists it multiplies the well count several-fold,
    and dropping the ones no sample lists removes exactly the wells the NTC rule acted on."""

    @pytest.mark.unit
    def test_control_well_appears_once_per_run(self, tmp_path):
        # RUN_A: two samples, both list NTC.
        out = extract_edna(write_run(tmp_path / 'a.xlsx', 'RUN_A', RUN_A_WELLS), META)
        ntc = well(out, 'NTC')                                  # exactly one row
        assert bool(ntc['is_control']) is True
        assert pd.isna(ntc['sample_code']) and pd.isna(ntc['Biomeme_sample_ID'])
        assert ntc['biomeme_run_name'] == 'RUN_A'
        assert sorted(out.loc[~out['is_control'], 'Biomeme replicate']) == ['5', '6']
        # presence.notna() is exactly the sample-row filter
        assert (out['is_control'] == out['presence'].isna()).all()

    @pytest.mark.unit
    def test_unlisted_control_well_is_kept_and_still_sets_the_floor(self, tmp_path):
        # The file has an NTC3 at Cq 29 that the metadata does not list. It rejects well 1
        # (28 ≥ 29 − 2) and is in the output to show why.
        meta = metadata([('RUN_U', '1,NTC', 'S1')])
        wells = [(1, '1', 28.0), (8, 'NTC', 0.0), (9, 'NTC3', 29.0)]
        out = extract_edna(write_run(tmp_path / 'u.xlsx', 'RUN_U', wells), meta)
        assert well(out, '1')['quality_flag'] == 4
        ntc3 = well(out, 'NTC3')
        assert bool(ntc3['is_control']) is True
        assert ntc3['Cq'] == 29.0 and pd.isna(ntc3['sample_code'])

    @pytest.mark.unit
    def test_control_rows_carry_run_level_metadata_only(self, tmp_path):
        meta = pd.DataFrame(
            [('RUN_R', '1,NTC', 'S1', 'TZ', '2025-09-11', 0.5)],
            columns=['biomeme_run_name', 'Biomeme_sample_ID', 'sample_code', 'country_code',
                     'sampling_date', 'dilution_factor'])
        wells = [(1, '1', 30.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'r.xlsx', 'RUN_R', wells), meta)
        ntc = well(out, 'NTC')
        assert ntc['country_code'] == 'TZ' and ntc['sampling_date'] == '2025-09-11'
        # the run's only sample does not lend its code or dilution to the control
        assert pd.isna(ntc['sample_code']) and pd.isna(ntc['dilution_factor'])
        assert well(out, '1')['sample_code'] == 'S1'

    @pytest.mark.unit
    def test_run_metadata_the_samples_disagree_on_is_left_empty(self, tmp_path):
        meta = pd.DataFrame(
            [('RUN_R', '1,NTC', 'S1', '2025-09-11'), ('RUN_R', '2,NTC', 'S2', '2025-09-12')],
            columns=['biomeme_run_name', 'Biomeme_sample_ID', 'sample_code', 'sampling_date'])
        wells = [(1, '1', 30.0), (2, '2', 30.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'r.xlsx', 'RUN_R', wells), meta)
        assert pd.isna(well(out, 'NTC')['sampling_date'])

    @pytest.mark.unit
    def test_controls_are_not_scored(self, tmp_path):
        meta = metadata([('RUN_D', '1,2,POS,NTC', 'S5')])
        wells = [(1, '1', 30.0), (2, '2', 31.0), (8, 'Pos', 20.0), (9, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'd.xlsx', 'RUN_D', wells), meta)
        pos, ntc = well(out, 'Pos'), well(out, 'NTC')
        assert pos['quality_flag'] == 0 and ntc['quality_flag'] == 3
        for col in ABUNDANCE_COLUMNS:
            assert pd.isna(pos[col]), f"POS row has {col} = {pos[col]!r}"
        assert pos['presence'] is None or pd.isna(pos['presence'])
        assert well(out, '1')['quality_flag'] == 1              # the sample is scored as before

    @pytest.mark.unit
    def test_run_without_metadata_rows_yields_nothing(self, tmp_path):
        # An unknown run has no samples to attach; its controls are not orphaned into the output.
        out = extract_edna(write_run(tmp_path / 'x.xlsx', 'RUN_X', RUN_A_WELLS), META)
        assert out.empty


class TestControlByWellNumber:
    """``NTC@9`` in the metadata: well 9 of the file is a no-template control, whatever the
    file labels it. Two 2025 runs had their NTC labelled as a sample number ('9') or not at
    all; the raw export stays as it is and the metadata carries the correction."""

    @pytest.mark.unit
    def test_mislabelled_ntc_is_a_control_and_sets_the_floor(self, tmp_path):
        meta = metadata([('RUN_O', '1,2,NTC@9', 'S1'), ('RUN_O', '3,4,NTC@9', 'S2')])
        wells = [(1, '1', 33.12), (2, '2', 33.66), (3, '3', 29.07), (4, '4', 27.35), (9, '9', 33.68)]
        out = extract_edna(write_run(tmp_path / 'o.xlsx', 'RUN_O', wells), meta)
        ntc = well(out, 'NTC')
        assert bool(ntc['is_control']) is True and ntc['Well Number'] == 9
        assert '9' not in set(out['Biomeme replicate'])
        assert well(out, '1')['quality_flag'] == 4 and well(out, '2')['quality_flag'] == 4
        assert well(out, '3')['quality_flag'] == 1 and well(out, '4')['quality_flag'] == 1
        assert well(out, '1')['presence'] == 'false' and well(out, '3')['presence'] == 'true'

    @pytest.mark.unit
    def test_unlabelled_well_can_be_named_a_control(self, tmp_path):
        # The file has NTC in well 8 (no amplification) and an unlabelled well 7 at Cq 34.47.
        meta = metadata([('RUN_U', '5,6,NTC,NTC@7', 'S1')])
        wells = [(5, '5', 31.75), (6, '6', 35.76), (7, None, 34.47), (8, 'NTC', 0.0)]
        out = extract_edna(write_run(tmp_path / 'u.xlsx', 'RUN_U', wells), meta)
        ntc = out[out['Biomeme replicate'] == 'NTC']
        assert sorted(ntc['Well Number']) == [7, 8] and ntc['is_control'].all()
        assert well(out, '5')['quality_flag'] == 1          # 2.7 cycles before the blank
        assert well(out, '6')['quality_flag'] == 4          # later than the blank
        assert well(out, '5')['presence'] == 'true'         # flag 1: the group had two amplifying wells

    @pytest.mark.unit
    def test_naming_a_sample_well_a_control_raises(self, tmp_path):
        meta = metadata([('RUN_O', '1,2,NTC@2', 'S1')])
        wells = [(1, '1', 30.0), (2, '2', 31.0)]
        with pytest.raises(ValueError, match='also listed as a sample well'):
            extract_edna(write_run(tmp_path / 'o.xlsx', 'RUN_O', wells), meta)

    @pytest.mark.unit
    @pytest.mark.parametrize('token', ['NTC@x', '5@9', 'NTC@'])
    def test_malformed_token_raises(self, tmp_path, token):
        meta = metadata([('RUN_O', f'1,2,{token}', 'S1')])
        wells = [(1, '1', 30.0), (2, '2', 31.0), (9, '9', 0.0)]
        with pytest.raises(ValueError, match='expected <control label>@<well number>'):
            extract_edna(write_run(tmp_path / 'o.xlsx', 'RUN_O', wells), meta)

    @pytest.mark.unit
    def test_missing_well_is_a_warning_not_an_error(self, tmp_path, capsys):
        meta = metadata([('RUN_O', '1,2,NTC@9', 'S1')])
        wells = [(1, '1', 30.0), (2, '2', 31.0)]
        out = extract_edna(write_run(tmp_path / 'o.xlsx', 'RUN_O', wells), meta)
        assert 'file has no such well' in capsys.readouterr().out
        assert well(out, '1')['quality_flag'] == 1


class TestExcludedAssays:
    """assay-exclusions.csv: a run's assay the lab has declared unreliable. Its sample wells
    are flagged 5 — neither a detection nor a negative — and its controls are left alone."""

    @pytest.fixture
    def exclusions(self, tmp_path, monkeypatch):
        def _write(text):
            path = tmp_path / 'assay-exclusions.csv'
            path.write_text('run_name,target_id,reason\n' + text, encoding='utf-8')
            monkeypatch.setenv('ODIN_ASSAY_EXCLUSIONS_PATH', str(path))
        return _write

    @pytest.mark.unit
    def test_excluded_target_wells_are_flagged_5(self, tmp_path, exclusions):
        exclusions('RUN_B,khe,primer stocks contaminated with gBlock DNA\n')
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        assert well(out, '5')['quality_flag'] == 5 and well(out, '6')['quality_flag'] == 5
        assert well(out, '5')['presence'] == 'false'
        assert well(out, 'NTC')['quality_flag'] == 3            # controls are not touched

    @pytest.mark.unit
    def test_star_excludes_every_target_of_the_run_only(self, tmp_path, exclusions):
        exclusions('RUN_B,*,whole run unreliable\n')
        out_b = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        out_a = extract_edna(write_run(tmp_path / 'a.xlsx', 'RUN_A', RUN_A_WELLS), META)
        assert (out_b.loc[~out_b['is_control'], 'quality_flag'] == 5).all()
        assert 5 not in set(out_a['quality_flag'])

    @pytest.mark.unit
    def test_other_target_is_not_excluded(self, tmp_path, exclusions):
        exclusions('RUN_B,ctxA,only the cholera assay\n')
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        assert well(out, '5')['quality_flag'] == 1

    @pytest.mark.unit
    def test_no_file_means_no_exclusions(self, tmp_path, monkeypatch):
        monkeypatch.setenv('ODIN_ASSAY_EXCLUSIONS_PATH', str(tmp_path / 'absent.csv'))
        out = extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
        assert well(out, '5')['quality_flag'] == 1

    @pytest.mark.unit
    def test_file_without_the_columns_is_refused(self, tmp_path, monkeypatch):
        path = tmp_path / 'assay-exclusions.csv'
        path.write_text('run,target\nRUN_B,Khe\n', encoding='utf-8')
        monkeypatch.setenv('ODIN_ASSAY_EXCLUSIONS_PATH', str(path))
        with pytest.raises(ValueError, match='missing columns'):
            extract_edna(write_run(tmp_path / 'b.xlsx', 'RUN_B', RUN_B_WELLS), META)
