"""
Unit tests for boris/model_import.py (parser, ethogram check, subject matching).

These exercise only the pure logic (parse_csv, match_behavior_code, match_subject_name,
detect_type_conflicts, build_import_plan) - no QApplication / running BORIS project needed.
Run from the tests/ directory, matching tests/Makefile.
"""

from decimal import Decimal as dec

import pytest

from boris import config as cfg
from boris import model_import as mi


ETHOGRAM = {
    "0": {"type": cfg.STATE_EVENT, "key": "", "code": "Sniff food outside", "modifiers": ""},
    "1": {"type": cfg.STATE_EVENT, "key": "", "code": "meal", "modifiers": ""},
    "2": {"type": cfg.POINT_EVENT, "key": "", "code": "Lick", "modifiers": ""},
}

SUBJECTS = {
    "0": {"key": "", "name": "Oliver", "description": ""},
    "1": {"key": "", "name": "Odin", "description": ""},
}


# --- behavior / subject matching -----------------------------------------------------------


def test_match_behavior_code_case_and_whitespace_insensitive():
    assert mi.match_behavior_code("sniff food outside", ETHOGRAM) == "Sniff food outside"
    assert mi.match_behavior_code("  Meal  ", ETHOGRAM) == "meal"
    assert mi.match_behavior_code("MEAL", ETHOGRAM) == "meal"


def test_match_behavior_code_beyond_case_is_a_mismatch():
    # "sitting" vs "sit" style difference must NOT auto-match
    assert mi.match_behavior_code("Sniff food", ETHOGRAM) is None
    assert mi.match_behavior_code("Zoomies", ETHOGRAM) is None


def test_match_subject_name_case_insensitive():
    assert mi.match_subject_name("oliver", SUBJECTS) == "Oliver"
    assert mi.match_subject_name("ODIN", SUBJECTS) == "Odin"


def test_match_subject_name_unmatched_or_blank_returns_none():
    assert mi.match_subject_name("Pagaille", SUBJECTS) is None
    assert mi.match_subject_name("", SUBJECTS) is None


# --- CSV parsing -----------------------------------------------------------------------------


def test_parse_csv_and_filter_by_observation(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "Observation id,Subject,Behavior,Behavior type,Time,Comment\n"
        "obsA,Odin,Sniff food outside,START,10.0,\n"
        "obsA,Odin,Sniff food outside,STOP,12.5,\n"
        "obsB,Oliver,Lick,POINT,5.0,\n",
        encoding="utf-8",
    )
    rows = mi.parse_csv(csv_path)
    assert len(rows) == 3

    obs_a_rows = mi.filter_for_observation(rows, "obsA")
    assert len(obs_a_rows) == 2
    assert obs_a_rows[0].time == dec("10.000")
    assert obs_a_rows[0].behavior_type == mi.START

    obs_b_rows = mi.filter_for_observation(rows, "obsB")
    assert len(obs_b_rows) == 1
    assert obs_b_rows[0].behavior_type == mi.POINT

    assert mi.filter_for_observation(rows, "obsC_does_not_exist") == []


def test_distinct_observation_ids_preserves_first_seen_order():
    csv_path_rows = [
        mi.ParsedRow("obsB", "Odin", "Lick", "POINT", dec("1.000"), ""),
        mi.ParsedRow("obsA", "Odin", "Lick", "POINT", dec("2.000"), ""),
        mi.ParsedRow("obsB", "Odin", "Lick", "POINT", dec("3.000"), ""),
    ]
    assert mi.distinct_observation_ids(csv_path_rows) == ["obsB", "obsA"]
    assert mi.distinct_observation_ids([]) == []


def test_parse_csv_missing_required_column(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    with pytest.raises(mi.MalformedCsvError):
        mi.parse_csv(csv_path)


def test_parse_csv_bad_behavior_type(tmp_path):
    csv_path = tmp_path / "bad_type.csv"
    csv_path.write_text(
        "Observation id,Subject,Behavior,Behavior type,Time,Comment\nobsA,Odin,Lick,MAYBE,1.0,\n",
        encoding="utf-8",
    )
    with pytest.raises(mi.MalformedCsvError):
        mi.parse_csv(csv_path)


def test_parse_csv_bad_time(tmp_path):
    csv_path = tmp_path / "bad_time.csv"
    csv_path.write_text(
        "Observation id,Subject,Behavior,Behavior type,Time,Comment\nobsA,Odin,Lick,POINT,not-a-number,\n",
        encoding="utf-8",
    )
    with pytest.raises(mi.MalformedCsvError):
        mi.parse_csv(csv_path)


# --- building the import plan -----------------------------------------------------------------


def _row(subject, behavior, behavior_type, time, comment=""):
    return mi.ParsedRow("obsA", subject, behavior, behavior_type, dec(str(time)).quantize(dec(".001")), comment)


def test_build_import_plan_state_pair_and_point_event():
    rows = [
        _row("Odin", "Sniff food outside", "START", "10.0"),
        _row("Odin", "Sniff food outside", "STOP", "12.5"),
        _row("Oliver", "Lick", "POINT", "5.0"),
    ]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS)

    assert result.skipped == []
    assert result.subject_free_count == 0
    assert sorted(result.events, key=lambda e: e[0]) == [
        [dec("5.000"), "Oliver", "Lick", "", ""],
        [dec("10.000"), "Odin", "Sniff food outside", "", ""],
        [dec("12.500"), "Odin", "Sniff food outside", "", ""],
    ]


def test_build_import_plan_unmatched_behavior_is_skipped():
    rows = [_row("Odin", "Zoomies", "POINT", "1.0")]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS)
    assert result.events == []
    assert len(result.skipped) == 1
    assert "Unknown behavior" in result.skipped[0].reason


def test_build_import_plan_unmatched_subject_loads_subject_free():
    rows = [_row("UnknownCat", "Lick", "POINT", "1.0")]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS)
    assert result.events == [[dec("1.000"), "", "Lick", "", ""]]
    assert result.subject_free_count == 1
    assert result.skipped == []


def test_build_import_plan_malformed_start_stop_sequence_is_skipped():
    # two STARTs in a row with no STOP in between can't be paired
    rows = [
        _row("Odin", "Sniff food outside", "START", "1.0"),
        _row("Odin", "Sniff food outside", "START", "2.0"),
    ]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS)
    assert result.events == []
    assert len(result.skipped) == 2
    assert all("Malformed" in s.reason for s in result.skipped)


# --- behavior-type conflicts --------------------------------------------------------------------


def test_detect_type_conflicts_finds_mismatch():
    # ethogram says Lick is a Point event, but the CSV has it as a START/STOP state
    rows = [
        _row("Odin", "Lick", "START", "1.0"),
        _row("Odin", "Lick", "STOP", "2.0"),
    ]
    conflicts = mi.detect_type_conflicts(rows, ETHOGRAM)
    assert set(conflicts) == {"Lick"}
    assert conflicts["Lick"].ethogram_type == cfg.POINT_EVENT
    assert conflicts["Lick"].csv_type == "STATE"
    assert conflicts["Lick"].row_count == 2


def test_detect_type_conflicts_no_conflict_when_types_agree():
    rows = [_row("Oliver", "Lick", "POINT", "5.0")]
    assert mi.detect_type_conflicts(rows, ETHOGRAM) == {}


def test_build_import_plan_skip_resolution_drops_conflicting_rows():
    rows = [
        _row("Odin", "Lick", "START", "1.0"),
        _row("Odin", "Lick", "STOP", "2.0"),
    ]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS, conflict_resolutions={"Lick": "skip"})
    assert result.events == []
    assert len(result.skipped) == 2
    assert all("type conflict" in s.reason for s in result.skipped)


# --- M3: unmatched-label finding, mapping rewrite, and project mutation -----------------------


def test_unmatched_behavior_labels_and_subject_names():
    rows = [
        _row("Odin", "Sniff food outside", "START", "1.0"),
        _row("Odin", "Sniff food outside", "STOP", "2.0"),
        _row("Odin", "Sniffing food", "POINT", "3.0"),  # unmatched behavior
        _row("Pagaille", "Lick", "POINT", "4.0"),  # unmatched subject
        _row("", "Lick", "POINT", "5.0"),  # blank subject - not "unmatched", just subject-free
    ]
    assert mi.unmatched_behavior_labels(rows, ETHOGRAM) == ["Sniffing food"]
    assert mi.unmatched_subject_names(rows, SUBJECTS) == ["Pagaille"]


def test_apply_behavior_mapping_rewrites_rows_in_place():
    rows = [_row("Odin", "Sniffing food", "POINT", "1.0")]
    mi.apply_behavior_mapping(rows, {"Sniffing food": "Sniff food outside"})
    assert rows[0].behavior_raw == "Sniff food outside"
    assert mi.match_behavior_code(rows[0].behavior_raw, ETHOGRAM) == "Sniff food outside"


def test_apply_subject_mapping_rewrites_rows_in_place():
    rows = [_row("Pagaille", "Lick", "POINT", "1.0")]
    mi.apply_subject_mapping(rows, {"Pagaille": "Odin"})
    assert rows[0].subject_raw == "Odin"


class _FakeMainWindow:
    """Minimal stand-in for MainWindow: just .pj plus no-op UI refresh methods."""

    def __init__(self, ethogram, subjects):
        self.pj = {cfg.ETHOGRAM: dict(ethogram), cfg.SUBJECTS: dict(subjects)}

    def load_behaviors_in_twEthogram(self, codes):
        pass

    def load_subjects_in_twSubjects(self, names):
        pass


def test_apply_behavior_resolutions_add_new():
    fake = _FakeMainWindow(ETHOGRAM, SUBJECTS)
    rows = [_row("Odin", "Zoomies", "POINT", "1.0")]
    mapping = mi.apply_behavior_resolutions(fake, {"Zoomies": ("add", "Zoomies")}, rows)
    assert mapping == {"Zoomies": "Zoomies"}
    added = [e for e in fake.pj[cfg.ETHOGRAM].values() if e[cfg.BEHAVIOR_CODE] == "Zoomies"]
    assert len(added) == 1
    assert added[0]["type"] == cfg.POINT_EVENT  # inferred from the row's own Behavior type


def test_apply_behavior_resolutions_map_to_existing():
    fake = _FakeMainWindow(ETHOGRAM, SUBJECTS)
    rows = [_row("Odin", "Sniffing food", "POINT", "1.0")]
    mapping = mi.apply_behavior_resolutions(fake, {"Sniffing food": ("map", "Sniff food outside")}, rows)
    assert mapping == {"Sniffing food": "Sniff food outside"}
    # no new entries created
    assert len(fake.pj[cfg.ETHOGRAM]) == len(ETHOGRAM)


def test_apply_behavior_resolutions_many_to_one_via_same_new_name():
    fake = _FakeMainWindow(ETHOGRAM, SUBJECTS)
    rows = [
        _row("Odin", "Zoomie", "POINT", "1.0"),
        _row("Odin", "Zoomies!", "POINT", "2.0"),
    ]
    mapping = mi.apply_behavior_resolutions(
        fake, {"Zoomie": ("add", "Zoomies"), "Zoomies!": ("add", "Zoomies")}, rows
    )
    assert mapping == {"Zoomie": "Zoomies", "Zoomies!": "Zoomies"}
    # only ONE new ethogram entry was created, even though two different raw labels chose "add"
    added = [e for e in fake.pj[cfg.ETHOGRAM].values() if e[cfg.BEHAVIOR_CODE] == "Zoomies"]
    assert len(added) == 1


def test_apply_subject_resolutions_add_and_many_to_one():
    fake = _FakeMainWindow(ETHOGRAM, SUBJECTS)
    mapping = mi.apply_subject_resolutions(fake, {"Pagaille": ("add", "Pagaille"), "pagaile (typo)": ("add", "Pagaille")})
    assert mapping == {"Pagaille": "Pagaille", "pagaile (typo)": "Pagaille"}
    added = [e for e in fake.pj[cfg.SUBJECTS].values() if e[cfg.SUBJECT_NAME] == "Pagaille"]
    assert len(added) == 1


def test_build_import_plan_use_csv_resolution_keeps_conflicting_rows():
    # caller is expected to have already updated the ethogram's type for "use_csv";
    # build_import_plan itself just stops skipping and pairs by the CSV's own markers
    rows = [
        _row("Odin", "Lick", "START", "1.0"),
        _row("Odin", "Lick", "STOP", "2.0"),
    ]
    result = mi.build_import_plan(rows, ETHOGRAM, SUBJECTS, conflict_resolutions={"Lick": "use_csv"})
    assert result.skipped == []
    assert sorted(result.events, key=lambda e: e[0]) == [
        [dec("1.000"), "Odin", "Lick", "", ""],
        [dec("2.000"), "Odin", "Lick", "", ""],
    ]
