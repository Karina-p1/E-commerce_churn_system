from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.complaints.forms import ComplaintFeedbackForm, ComplaintForm
from apps.complaints.models import Complaint
from apps.orders.models import Order


User = get_user_model()


def valid_complaint_payload(**overrides):
    payload = {
        "order": "",
        "complaint_type": "DELIVERY",
        "subject": "Package arrived damaged",
        "description": (
            "The outer box was crushed on arrival and the item inside was "
            "already broken when I opened it."
        ),
    }
    payload.update(overrides)
    return payload


class ComplaintFormTests(TestCase):

    def test_accepts_a_valid_complaint(self):
        form = ComplaintForm(data=valid_complaint_payload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_complaint_without_an_order_is_allowed(self):
        """Complaint.order is null=True on the model — general site
        complaints have nothing to attach to."""
        form = ComplaintForm(data=valid_complaint_payload(order=""))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["order"])

    def test_requires_a_complaint_type(self):
        form = ComplaintForm(data=valid_complaint_payload(complaint_type=""))

        self.assertFalse(form.is_valid())
        self.assertIn("complaint_type", form.errors)

    def test_rejects_a_missing_subject(self):
        form = ComplaintForm(data=valid_complaint_payload(subject=""))

        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)

    def test_rejects_a_too_short_description(self):
        form = ComplaintForm(data=valid_complaint_payload(description="bad"))

        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_rejects_a_description_made_of_symbols_only(self):
        form = ComplaintForm(data=valid_complaint_payload(description="!." * 15))

        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_rejects_repeating_the_subject_as_the_description(self):
        form = ComplaintForm(
            data=valid_complaint_payload(
                subject="Package arrived damaged",
                description="Package arrived damaged",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_rejects_an_order_belonging_to_someone_else(self):
        other = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="test-password-123",
        )

        order = Order.objects.create(user=other, total_price=1000)

        form = ComplaintForm(data=valid_complaint_payload(order=order.pk))

        self.assertFalse(form.is_valid())
        self.assertIn("order", form.errors)

    def test_rejects_a_non_numeric_order_reference(self):
        form = ComplaintForm(data=valid_complaint_payload(order="abc"))

        self.assertFalse(form.is_valid())
        self.assertIn("order", form.errors)


class ComplaintFeedbackFormTests(TestCase):

    def test_accepts_feedback_for_a_high_rating(self):
        form = ComplaintFeedbackForm(
            data={
                "customer_rating": "5",
                "customer_feedback": "Handled very quickly, thanks.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_accepts_no_feedback_for_a_high_rating(self):
        form = ComplaintFeedbackForm(
            data={"customer_rating": "4", "customer_feedback": ""}
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_feedback_for_a_low_rating(self):
        form = ComplaintFeedbackForm(
            data={"customer_rating": "2", "customer_feedback": ""}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("customer_feedback", form.errors)

    def test_requires_feedback_for_the_middle_rating(self):
        form = ComplaintFeedbackForm(
            data={"customer_rating": "3", "customer_feedback": "no"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("customer_feedback", form.errors)

    def test_requires_a_rating(self):
        form = ComplaintFeedbackForm(
            data={"customer_rating": "", "customer_feedback": "Some text"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("customer_rating", form.errors)

    def test_rejects_a_rating_outside_one_to_five(self):
        form = ComplaintFeedbackForm(
            data={"customer_rating": "9", "customer_feedback": "Nope, too long"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("customer_rating", form.errors)


class ComplaintViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_valid_complaint_is_saved(self):
        response = self.client.post(
            reverse("complaints:create"),
            valid_complaint_payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Complaint.objects.count(), 1)

    def test_invalid_complaint_re_renders_the_form(self):
        response = self.client.post(
            reverse("complaints:create"),
            valid_complaint_payload(description=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)


class AdminComplaintUpdateTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.complaint = Complaint.objects.create(
            user=self.staff,
            complaint_type="DELIVERY",
            subject="Damaged box",
            description="The outer box was crushed on arrival and it was broken.",
        )
        self.client.force_login(self.staff)
        self.url = reverse(
            "complaints:complaint_detail", args=[self.complaint.pk]
        )

    def test_rejects_an_unknown_status(self):
        response = self.client.post(
            self.url,
            {
                "status": "teleported",
                "priority": "LOW",
                "admin_reply": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertNotEqual(self.complaint.status, "teleported")

    def test_rejects_an_unknown_priority(self):
        response = self.client.post(
            self.url,
            {
                "status": "PENDING",
                "priority": "extremely-urgent",
                "admin_reply": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertNotEqual(self.complaint.priority, "extremely-urgent")

    def test_rejects_an_over_long_reply(self):
        response = self.client.post(
            self.url,
            {
                "status": "PENDING",
                "priority": "LOW",
                "admin_reply": "x" * 5001,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertNotEqual(len(self.complaint.admin_reply or ""), 5001)

    def test_accepts_a_valid_update(self):
        response = self.client.post(
            self.url,
            {
                "status": "RESOLVED",
                "priority": "HIGH",
                "admin_reply": "We have issued a replacement for your order.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, "RESOLVED")
        self.assertEqual(self.complaint.priority, "HIGH")


class ComplaintTemplateRenderTests(TestCase):
    """
    Every template touched by the validation work has to render, including
    the error branches that only run after a rejected POST.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.order = Order.objects.create(user=self.user, total_price=1000)
        self.complaint = Complaint.objects.create(
            user=self.user,
            order=self.order,
            complaint_type="DELIVERY",
            subject="Damaged box",
            description="The outer box was crushed on arrival and it was broken.",
        )
        # Only a resolved complaint collects customer feedback.
        self.complaint.status = "RESOLVED"
        self.complaint.save()

    def test_complaint_form_renders(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("complaints:create"))

        self.assertEqual(response.status_code, 200)

    def test_complaint_form_renders_with_errors(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("complaints:create"),
            valid_complaint_payload(description=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "errorlist")

    def test_feedback_form_renders(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("complaints:feedback", args=[self.complaint.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_feedback_form_renders_with_errors(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("complaints:feedback", args=[self.complaint.pk]),
            {"customer_rating": "1", "customer_feedback": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_admin_complaint_detail_renders(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("complaints:complaint_detail", args=[self.complaint.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="admin_reply"')
        self.assertContains(response, "maxlength=\"5000\"")
