"""Tests for the GetAttrs coercion table.

Expectations were captured by calling the real
``Posda::DB::Modules::GetAttrs`` inside the container with the same parameter
tables and diffing both the values and the error strings.
"""

from posda.ingest.coercions import (
    date,
    get_attrs,
    integer,
    multi_text,
    timetag,
    undef_if_not_number,
)


class TestDate:
    def test_valid_date_is_reformatted(self):
        errors: list[str] = []
        assert date("19700615", "dob", errors) == "1970/06/15"
        assert errors == []

    def test_empty_string_is_rejected(self):
        # This single case accounts for every dicom_process_errors row in the
        # dev database: 'Bad date "" in dob', one per file.
        errors: list[str] = []
        assert date("", "dob", errors) is None
        assert errors == ['Bad date "" in dob']

    def test_none_passes_through_without_an_error(self):
        errors: list[str] = []
        assert date(None, "dob", errors) is None
        assert errors == []

    def test_undef_sentinel_is_silently_dropped(self):
        errors: list[str] = []
        assert date("<undef> ", "dob", errors) is None
        assert errors == []

    def test_month_out_of_range_is_rejected(self):
        errors: list[str] = []
        assert date("20241301", "study_date", errors) is None
        assert errors == ['Bad date "20241301" in study_date']

    def test_short_date_padded_to_eight_becomes_a_wrong_but_valid_date(self):
        # "1970061 " is a malformed DA that DA's lack of trailing-strip lets
        # through. The regex takes day = "1 ", Perl numifies that to 1, and
        # the result is a plausible-looking date that is not the real one.
        errors: list[str] = []
        assert date("1970061 ", "dob", errors) == "1970/06/01"
        assert errors == []

    def test_blank_year_is_rejected(self):
        errors: list[str] = []
        assert date("    0615", "dob", errors) is None
        assert errors == ['Bad date "    0615" in dob']

    def test_unknown_year_is_rejected(self):
        errors: list[str] = []
        assert date("????0615", "dob", errors) is None
        assert errors == ['Bad date "????0615" in dob']

    def test_space_padded_month_and_day_are_zero_filled(self):
        errors: list[str] = []
        assert date("1970 6 5", "dob", errors) == "1970/06/05"
        assert errors == []


class TestTimetag:
    def test_plain_time(self):
        errors: list[str] = []
        assert timetag("143000", "study_time", errors) == "14:30:00"
        assert errors == []

    def test_fractional_time(self):
        errors: list[str] = []
        assert timetag("143005.25", "series_time", errors) == "14:30:05.25"
        assert errors == []

    def test_short_time_is_rejected(self):
        errors: list[str] = []
        assert timetag("0930", "study_time", errors) is None
        assert errors == ['Bad time "0930" in study_time']

    def test_garbage_is_rejected(self):
        errors: list[str] = []
        assert timetag("99xx99", "study_time", errors) is None
        assert errors == ['Bad time "99xx99" in study_time']

    def test_none_passes_through_without_an_error(self):
        errors: list[str] = []
        assert timetag(None, "study_time", errors) is None
        assert errors == []


class TestMultiText:
    def test_list_is_joined_with_backslash(self):
        assert multi_text(["A", "B", "C"], "image_type", []) == "A\\B\\C"

    def test_scalar_passes_through(self):
        assert multi_text("A", "image_type", []) == "A"

    def test_none_passes_through(self):
        assert multi_text(None, "image_type", []) is None


class TestUndefIfNotNumber:
    def test_integer_text_is_returned_unchanged(self):
        assert undef_if_not_number("12", "series_number", []) == "12"

    def test_surrounding_whitespace_is_preserved(self):
        # The regex tolerates whitespace and the original string is returned,
        # so the column keeps the padding.
        assert undef_if_not_number(" 12 ", "series_number", []) == " 12 "

    def test_non_numeric_is_rejected(self):
        errors: list[str] = []
        assert undef_if_not_number("abc", "series_number", errors) is None
        assert errors == ['Bad number "abc" in series_number']

    def test_decimal_is_rejected(self):
        errors: list[str] = []
        assert undef_if_not_number("1.5", "series_number", errors) is None
        assert errors == ['Bad number "1.5" in series_number']


class TestInteger:
    def test_integral_value(self):
        errors: list[str] = []
        assert integer("42", "n", errors) == 42
        assert errors == []

    def test_fractional_value_truncates_and_complains(self):
        errors: list[str] = []
        assert integer("42.7", "n", errors) == 42
        assert errors == ["Error making 42.7 an integer\n"]


class TestGetAttrs:
    class FakeValues:
        def __init__(self, mapping):
            self.mapping = mapping

        def get(self, sig):
            return self.mapping.get(sig)

    def test_reads_every_param_and_coerces_named_ones(self):
        values = self.FakeValues({"(0010,0030)": "19700615", "(0010,0020)": "PAT001"})
        errors: list[str] = []
        got = get_attrs(
            values,
            {"dob": "(0010,0030)", "patient_id": "(0010,0020)"},
            {"dob": "Date"},
            errors,
        )
        assert got == {"dob": "1970/06/15", "patient_id": "PAT001"}
        assert errors == []

    def test_missing_params_are_present_as_none(self):
        values = self.FakeValues({})
        got = get_attrs(values, {"dob": "(0010,0030)"}, {}, [])
        assert got == {"dob": None}

    def test_unknown_coercion_name_leaves_the_value_alone(self):
        values = self.FakeValues({"(0010,0030)": "19700615"})
        got = get_attrs(values, {"dob": "(0010,0030)"}, {"dob": "Nope"}, [])
        assert got == {"dob": "19700615"}
