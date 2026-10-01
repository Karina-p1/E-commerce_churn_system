from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.addresses.forms import AddressForm
from apps.addresses.models import Address


User = get_user_model()


def valid_address_payload(**overrides):
    payload = {
        "label": "Home",
        "full_name": "Saugat Karki",
        "phone": "9812345678",
        "province": "Bagmati",
        "district": "Kathmandu",
        "city": "Kathmandu",
        "ward": "4",
        "street": "Baneshwor 5",
        "landmark": "",
        "latitude": "27.67890000",
        "longitude": "85.31230000",
    }
    payload.update(overrides)
    return payload


class AddressFormTests(TestCase):

    def test_accepts_a_complete_address(self):
        form = AddressForm(data=valid_address_payload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_a_missing_phone(self):
        form = AddressForm(data=valid_address_payload(phone=""))

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_rejects_a_non_mobile_phone(self):
        form = AddressForm(data=valid_address_payload(phone="1234567890"))

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_rejects_an_out_of_range_ward(self):
        form = AddressForm(data=valid_address_payload(ward="0"))

        self.assertFalse(form.is_valid())
        self.assertIn("ward", form.errors)

    def test_rejects_a_street_that_is_too_short(self):
        form = AddressForm(data=valid_address_payload(street="ab"))

        self.assertFalse(form.is_valid())
        self.assertIn("street", form.errors)

    def test_rejects_a_name_containing_digits(self):
        form = AddressForm(data=valid_address_payload(full_name="Saugat 98"))

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)

    def test_rejects_out_of_range_coordinates(self):
        form = AddressForm(data=valid_address_payload(latitude="120"))

        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

    def test_rejects_half_a_coordinate_pair(self):
        """The map writes both coordinates or neither."""
        form = AddressForm(
            data=valid_address_payload(longitude="")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

    def test_allows_no_coordinates_at_all(self):
        form = AddressForm(
            data=valid_address_payload(latitude="", longitude="")
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_normalizes_the_phone_number(self):
        form = AddressForm(data=valid_address_payload(phone="+977 9812345678"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "9812345678")


class AddAddressViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_valid_submission_saves_the_address(self):
        response = self.client.post(
            "/addresses/add/",
            valid_address_payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 1)

    def test_invalid_submission_re_renders_with_errors(self):
        response = self.client.post(
            "/addresses/add/",
            valid_address_payload(phone="123"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Address.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, "valid Nepali mobile number")
