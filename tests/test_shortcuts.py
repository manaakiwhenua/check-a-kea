import pytest
from core.shortcuts import normalise_key, shortcut_conflicts


# ------------------------------------------------------------------ normalise_key


class TestNormaliseKey:
    # Digits
    def test_single_digit_unchanged(self):
        assert normalise_key("1") == "1"

    def test_multi_digit_expanded_to_sequence(self):
        assert normalise_key("55") == "5, 5"

    def test_three_digit_expanded(self):
        assert normalise_key("120") == "1, 2, 0"

    # Bare letters — single
    def test_lowercase_letter_uppercased(self):
        assert normalise_key("e") == "E"

    def test_uppercase_letter_becomes_shift_combo(self):
        assert normalise_key("E") == "Shift+E"

    def test_lowercase_a(self):
        assert normalise_key("a") == "A"

    def test_uppercase_a_becomes_shift(self):
        assert normalise_key("A") == "Shift+A"

    # Multi-char alpha — uniform case
    def test_all_lowercase_alpha_expanded(self):
        assert normalise_key("aa") == "A, A"

    def test_all_uppercase_alpha_expanded(self):
        assert normalise_key("BB") == "Shift+B, Shift+B"

    def test_lowercase_word_expanded(self):
        assert normalise_key("ok") == "O, K"

    def test_uppercase_word_expanded(self):
        assert normalise_key("OK") == "Shift+O, Shift+K"

    # Multi-char alpha — mixed case
    def test_mixed_case_expanded_per_char(self):
        assert normalise_key("aB") == "A, Shift+B"

    def test_mixed_case_word(self):
        # 'O' is uppercase → Shift+O; 'k' is lowercase → K
        assert normalise_key("Ok") == "Shift+O, K"

    # Modifier + letter combos
    def test_shift_lowercase_uppercases_key(self):
        assert normalise_key("shift+e") == "shift+E"

    def test_shift_uppercase_unchanged(self):
        assert normalise_key("Shift+E") == "Shift+E"

    def test_ctrl_lowercase_uppercases_key(self):
        assert normalise_key("ctrl+a") == "ctrl+A"

    def test_multi_modifier_uppercases_key(self):
        assert normalise_key("Ctrl+Shift+z") == "Ctrl+Shift+Z"

    # Named / special keys — must not be altered
    # Named keys with digits are left alone (isalpha() is False)
    def test_f1_unchanged(self):
        assert normalise_key("F1") == "F1"

    # Edge cases
    def test_empty_string_unchanged(self):
        assert normalise_key("") == ""

    def test_whitespace_stripped(self):
        assert normalise_key("  e  ") == "E"


# ------------------------------------------------------------------ shortcut_conflicts


class TestShortcutConflicts:
    def test_empty_list(self):
        assert shortcut_conflicts([]) == set()

    def test_no_conflicts(self):
        assert shortcut_conflicts(["1", "2", "3"]) == set()

    def test_duplicate_keys_both_flagged(self):
        assert shortcut_conflicts(["1", "1", "2"]) == {"1"}

    def test_prefix_conflict_both_flagged(self):
        assert shortcut_conflicts(["1", "10"]) == {"1", "10"}

    def test_equal_length_no_conflict(self):
        assert shortcut_conflicts(["10", "11", "12"]) == set()

    def test_short_key_conflicts_with_all_extensions(self):
        assert shortcut_conflicts(["1", "10", "11"]) == {"1", "10", "11"}

    def test_three_digit_codes_no_conflict(self):
        assert shortcut_conflicts(["120", "290", "314"]) == set()

    def test_empty_strings_ignored(self):
        assert shortcut_conflicts(["", "1", "2"]) == set()

    def test_all_empty_strings(self):
        assert shortcut_conflicts(["", "", ""]) == set()

    def test_digit_run_and_single_digit_conflict(self):
        # "55" and "5" — "55".startswith("5") is True
        assert shortcut_conflicts(["55", "5"]) == {"55", "5"}

    def test_expanded_sequence_and_single_digit_conflict(self):
        # same logic applies to Qt expanded form "5, 5"
        assert shortcut_conflicts(["5, 5", "5"]) == {"5, 5", "5"}

    def test_reversed_prefix_also_conflicts(self):
        assert shortcut_conflicts(["10", "1"]) == {"10", "1"}
