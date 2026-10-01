"""
Shared input-validation helpers for the ShopMart project.

Two kinds of consumers use this module:

1. Django forms (``apps/*/forms.py``) call the ``validate_*`` helpers from
   their ``clean_<field>()`` / ``clean()`` methods.
2. The hand-built admin and customer forms in ``apps/*/views.py`` call the
   ``parse_*`` helpers, which return ``(value, error)`` so a view can
   collect every problem in a submission and show them all at once instead
   of failing on the first one.

Keeping both kinds in one place means a rule like "phone must be a valid
Nepali mobile number" is written once instead of being copy-pasted into
each form and slowly drifting out of sync.
"""

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime


# Nepali mobile numbers are 10 digits and start with 9 (96/97/98 prefixes).
# Users routinely type them with a +977, 977 or 0 country prefix, so those
# are stripped before the local format is matched.
LOCAL_MOBILE_RE = re.compile(r"^9\d{9}$")

DIGITS_ONLY_RE = re.compile(r"^\d+$")
ONLY_SYMBOLS_RE = re.compile(r"^[^\w\s]+$", re.UNICODE)

MAX_IMAGE_BYTES = 5 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
}


# ---------------------------------------------------------------------------
# PHONE NUMBERS
# ---------------------------------------------------------------------------


def normalize_phone(raw):
    """Strip separators and the +977 / 977 / 0 country prefix."""
    digits = re.sub(r"[^\d+]", "", str(raw or ""))

    if digits.startswith("+"):
        digits = digits[1:]

    if digits.startswith("977"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]

    return digits


def validate_phone(raw, required=True, field_name="Phone number"):
    """
    Return the 10-digit local form of a Nepali mobile number, or raise
    ValidationError with a message the customer can act on.
    """
    digits = normalize_phone(raw)

    if not digits:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return ""

    if not LOCAL_MOBILE_RE.match(digits):
        raise ValidationError(
            f"{field_name} must be a valid Nepali mobile number "
            f"(10 digits starting with 9, e.g. 9812345678)."
        )

    return digits


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------


def validate_text(
    raw,
    field_name,
    required=True,
    min_length=None,
    max_length=None,
    allow_symbols_only=False,
):
    """Trim a value and enforce presence / length rules."""
    value = str(raw or "").strip()

    if not value:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return ""

    if allow_symbols_only is False and ONLY_SYMBOLS_RE.match(value):
        raise ValidationError(f"{field_name} can't be only symbols.")

    if min_length is not None and len(value) < min_length:
        raise ValidationError(
            f"{field_name} must be at least {min_length} characters long."
        )

    if max_length is not None and len(value) > max_length:
        raise ValidationError(
            f"{field_name} must be {max_length} characters or fewer."
        )

    return value


def validate_name(raw, field_name="Name", max_length=150):
    """A person or account name: at least two letters, no stray digits."""
    value = validate_text(
        raw,
        field_name,
        required=True,
        min_length=2,
        max_length=max_length,
    )

    if not re.search(r"[A-Za-z\u0900-\u097F]", value):
        raise ValidationError(f"{field_name} must contain letters.")

    if re.search(r"\d", value):
        raise ValidationError(f"{field_name} can't contain numbers.")

    return value


def validate_digits(raw, field_name, min_length=1, max_length=50):
    """A digits-only identifier such as a bank account number."""
    value = str(raw or "").strip().replace(" ", "").replace("-", "")

    if not value:
        raise ValidationError(f"{field_name} is required.")

    if not DIGITS_ONLY_RE.match(value):
        raise ValidationError(f"{field_name} must contain digits only.")

    if not (min_length <= len(value) <= max_length):
        raise ValidationError(
            f"{field_name} must be between {min_length} and "
            f"{max_length} digits long."
        )

    return value


# ---------------------------------------------------------------------------
# FILES
# ---------------------------------------------------------------------------


def validate_image(uploaded_file, field_name="Image", max_bytes=MAX_IMAGE_BYTES):
    """
    Reject uploads that are empty, too large, or not an image.

    The model field is an ImageField, but that check only runs when the file
    is actually assigned — Pillow still has to open it, and an oversized or
    wrongly-typed upload otherwise fails deep inside the save with an
    unhelpful traceback.
    """
    if uploaded_file is None:
        return

    if getattr(uploaded_file, "size", 0) == 0:
        raise ValidationError(f"{field_name} is empty.")

    if uploaded_file.size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise ValidationError(
            f"{field_name} must be smaller than {limit_mb:g} MB."
        )

    content_type = getattr(uploaded_file, "content_type", None)

    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(
            f"{field_name} must be a JPG, PNG, GIF or WEBP image."
        )


# ---------------------------------------------------------------------------
# PARSERS FOR HAND-BUILT FORMS
# ---------------------------------------------------------------------------
#
# These never raise. They return (value, error) where error is None on
# success, so a view can gather every problem in a submission and show them
# together. The `default` is returned on failure so the calling view can
# keep rendering the page without worrying about None.


def parse_text(
    raw,
    label,
    required=True,
    min_length=None,
    max_length=None,
    default="",
):
    try:
        return (
            validate_text(
                raw,
                label,
                required=required,
                min_length=min_length,
                max_length=max_length,
            ),
            None,
        )
    except ValidationError as exc:
        return default, exc.messages[0]


def parse_int(
    raw,
    label,
    required=True,
    min_value=None,
    max_value=None,
    default=None,
):
    value = str(raw or "").strip()

    if not value:
        if required:
            return default, f"{label} is required."
        return default, None

    try:
        number = int(value)
    except ValueError:
        return default, f"{label} must be a whole number."

    if min_value is not None and number < min_value:
        return default, f"{label} cannot be less than {min_value}."

    if max_value is not None and number > max_value:
        return default, f"{label} cannot be greater than {max_value}."

    return number, None


def parse_decimal(
    raw,
    label,
    required=True,
    min_value=None,
    max_value=None,
    default=None,
):
    value = str(raw or "").strip()

    if not value:
        if required:
            return default, f"{label} is required."
        return default, None

    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return default, f"{label} must be a valid number."

    if number < 0 and (min_value is None or min_value >= 0):
        return default, f"{label} cannot be negative."

    if min_value is not None and number < Decimal(str(min_value)):
        return default, f"{label} must be at least {min_value}."

    if max_value is not None and number > Decimal(str(max_value)):
        return default, f"{label} must be at most {max_value}."

    return number, None


def parse_choice(raw, label, choices, default=None):
    """Check a value against a list of (value, label) model choices."""
    valid_values = [choice[0] for choice in choices]

    if raw not in valid_values:
        return default, f"Invalid {label}."

    return raw, None


def parse_phone(raw, label="Phone number", required=True, default=""):
    try:
        return validate_phone(raw, required=required, field_name=label), None
    except ValidationError as exc:
        return default, exc.messages[0]


def parse_image(uploaded_file, label="Image", max_bytes=MAX_IMAGE_BYTES):
    try:
        validate_image(uploaded_file, label, max_bytes)
    except ValidationError as exc:
        return None, exc.messages[0]

    return uploaded_file, None


# ---------------------------------------------------------------------------
# DATE / TIME
# ---------------------------------------------------------------------------


def to_aware(value):
    """Attach the current timezone to a naive datetime."""
    if value is None:
        return None

    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())

    return value


def parse_datetime_input(raw, label, required=False):
    """
    Parse a `datetime-local` / ISO-8601 string into an aware datetime.

    Returns (value, error). An empty value is allowed unless required, and
    yields (None, None) — the model fields for these are nullable, so
    "no date set" and "invalid date" have to stay distinguishable.
    """
    value = str(raw or "").strip()

    if not value:
        if required:
            return None, f"{label} is required."
        return None, None

    parsed = parse_datetime(value)

    if parsed is None:
        return None, f"{label} is not a valid date and time."

    return to_aware(parsed), None
