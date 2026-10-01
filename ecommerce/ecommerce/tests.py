from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from ecommerce.validators import (
    normalize_phone,
    parse_choice,
    parse_datetime_input,
    parse_decimal,
    parse_int,
    parse_text,
    validate_digits,
    validate_name,
    validate_phone,
    validate_text,
)


class NormalizePhoneTests(SimpleTestCase):

    def test_strips_country_prefixes(self):
        for raw in (
            "9812345678",
            "+9779812345678",
            "9779812345678",
            "09812345678",
            "98 1234 5678",
            "98-1234-5678",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "9812345678")


class ValidatePhoneTests(SimpleTestCase):

    def test_accepts_valid_numbers(self):
        self.assertEqual(validate_phone("9812345678"), "9812345678")
        self.assertEqual(validate_phone("+977 981 234 5678"), "9812345678")

    def test_rejects_landline_and_short_numbers(self):
        for raw in ("1234567890", "981234567", "98123456789", "abcdefghij"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validate_phone(raw)

    def test_blank_is_an_error_when_required(self):
        with self.assertRaises(ValidationError):
            validate_phone("   ")

    def test_blank_is_allowed_when_optional(self):
        self.assertEqual(validate_phone("", required=False), "")


class ValidateTextTests(SimpleTestCase):

    def test_strips_whitespace(self):
        self.assertEqual(validate_text("  Kathmandu  ", "City"), "Kathmandu")

    def test_enforces_min_and_max_length(self):
        with self.assertRaises(ValidationError):
            validate_text("ab", "Label", min_length=3)

        with self.assertRaises(ValidationError):
            validate_text("abcd", "Label", max_length=3)

    def test_rejects_symbol_only_values(self):
        with self.assertRaises(ValidationError):
            validate_text("!!!", "Description")

    def test_blank_only_rejected_when_required(self):
        self.assertEqual(validate_text("  ", "Landmark", required=False), "")


class ValidateNameTests(SimpleTestCase):

    def test_accepts_ordinary_names(self):
        self.assertEqual(validate_name("Saugat Karki"), "Saugat Karki")

    def test_rejects_digits(self):
        with self.assertRaises(ValidationError):
            validate_name("Saugat 9812345678")

    def test_rejects_single_letter(self):
        with self.assertRaises(ValidationError):
            validate_name("S")


class ValidateDigitsTests(SimpleTestCase):

    def test_strips_spaces_and_dashes(self):
        self.assertEqual(
            validate_digits("1234 5678-9012", "Account number"),
            "123456789012",
        )

    def test_rejects_non_digits(self):
        with self.assertRaises(ValidationError):
            validate_digits("12AB3456", "Account number")

    def test_enforces_length_bounds(self):
        with self.assertRaises(ValidationError):
            validate_digits("12", "Account number", min_length=4)

        with self.assertRaises(ValidationError):
            validate_digits("1" * 60, "Account number", max_length=50)


class ParseHelperTests(SimpleTestCase):
    """
    The parse_* helpers return (value, error) instead of raising, so a
    view can report every problem in a submission at once.
    """

    def test_parse_text_success_and_failure(self):
        self.assertEqual(parse_text(" Nike ", "Name"), ("Nike", None))

        value, error = parse_text("", "Name")

        self.assertEqual(value, "")
        self.assertEqual(error, "Name is required.")

    def test_parse_int(self):
        self.assertEqual(parse_int("12", "Stock", min_value=0), (12, None))

        self.assertEqual(parse_int("", "Stock", required=False), (None, None))

        _, error = parse_int("abc", "Stock")
        self.assertEqual(error, "Stock must be a whole number.")

        _, error = parse_int("-1", "Stock", min_value=0)
        self.assertEqual(error, "Stock cannot be less than 0.")

        _, error = parse_int("101", "Stock", max_value=100)
        self.assertEqual(error, "Stock cannot be greater than 100.")

    def test_parse_decimal(self):
        value, error = parse_decimal("12.50", "Price")
        self.assertEqual(error, None)
        self.assertEqual(str(value), "12.50")

        _, error = parse_decimal("abc", "Price")
        self.assertEqual(error, "Price must be a valid number.")

        _, error = parse_decimal("-5", "Price")
        self.assertEqual(error, "Price cannot be negative.")

    def test_parse_choice(self):
        self.assertEqual(
            parse_choice("COD", "payment method", [("COD", "Cash")]),
            ("COD", None),
        )

        value, error = parse_choice(
            "BOGUS",
            "payment method",
            [("COD", "Cash")],
        )

        self.assertIsNone(value)
        self.assertEqual(error, "Invalid payment method.")

    def test_parse_datetime_input(self):
        value, error = parse_datetime_input("", "Valid from")
        self.assertEqual((value, error), (None, None))

        value, error = parse_datetime_input("2026-01-31T10:00", "Valid from")
        self.assertIsNone(error)
        self.assertEqual((value.year, value.month, value.day), (2026, 1, 31))
        self.assertIsNotNone(value.tzinfo)

        value, error = parse_datetime_input("not-a-date", "Valid from")
        self.assertIsNone(value)
        self.assertEqual(error, "Valid from is not a valid date and time.")
