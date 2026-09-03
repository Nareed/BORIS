"""
Unit tests for boris/event_stamping.py's pure color-ranking logic (SPEC.md §2, M4).
No QApplication needed for subject_color() - it's plain string/list logic.
"""

from boris import event_stamping as es

REAL_PROJECT_SUBJECTS = ["Oliver", "Odin", "Orwell", "Pagaille", "Ortide", "Otaria", "Oupla", "Oui-Oui", "Olivette", "Oumous"]


def test_subject_color_blank_name_returns_empty_string():
    assert es.subject_color("", REAL_PROJECT_SUBJECTS) == ""


def test_subject_color_is_deterministic_across_calls():
    assert es.subject_color("Oliver", REAL_PROJECT_SUBJECTS) == es.subject_color("Oliver", REAL_PROJECT_SUBJECTS)


def test_subject_color_is_a_hex_color():
    color = es.subject_color("Odin", REAL_PROJECT_SUBJECTS)
    assert color.startswith("#")
    assert len(color) == 7
    int(color[1:], 16)  # raises if not valid hex


def test_subject_color_no_collisions_within_a_real_project_subject_list():
    # this is the actual point of ranking by position instead of hashing each name in
    # isolation: pure independent hashing produced only 6 distinct colors for these same
    # 10 names against an 18-color palette (confirmed while building this) - not usable as
    # a "color legend". Ranking guarantees a distinct color per subject as long as the
    # project has no more subjects than palette colors.
    colors = {es.subject_color(n, REAL_PROJECT_SUBJECTS) for n in REAL_PROJECT_SUBJECTS}
    assert len(colors) == len(REAL_PROJECT_SUBJECTS)


def test_subject_color_stable_regardless_of_input_list_order():
    # ranking is by sorted name, not by the order subject_names happens to be passed in
    # (e.g. dict.values() iteration order, which reflects insertion, not name)
    shuffled = list(reversed(REAL_PROJECT_SUBJECTS))
    assert es.subject_color("Oliver", REAL_PROJECT_SUBJECTS) == es.subject_color("Oliver", shuffled)


def test_subject_color_cycles_palette_beyond_its_size():
    many_subjects = [f"Cat{i}" for i in range(40)]  # more than the 18-color palette
    # no crash, and it's still a valid color
    color = es.subject_color("Cat39", many_subjects)
    assert color.startswith("#")
