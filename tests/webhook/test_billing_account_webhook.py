"""Tests for webhook billing account integration."""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from drf_stripe.models import Subscription, SubscriptionItem, StripeUser
from drf_stripe.settings import drf_stripe_settings
from drf_stripe.stripe_webhooks.handler import handle_webhook_event
from tests.base import BaseTest
from tests.models import Company


class TestWebhookBillingAccountIntegration(BaseTest):
    """Test that webhook handlers integrate with billing account correctly."""

    def setUp(self) -> None:
        self.setup_product_prices()
        # Create a user and a company with that user as manager
        self.user = get_user_model().objects.create(
            username="tester",
            email="tester1@example.com",
            password="12345"
        )
        self.company = Company.objects.create(
            name="Test Company",
            manager_user=self.user
        )
        # Create StripeUser for the test user
        self.stripe_user = StripeUser.objects.create(
            user_id=self.user.id,
            customer_id="cus_tester"
        )

    def get_billing_settings(self):
        """Return DRF_STRIPE settings with BILLING_ACCOUNT_MODEL configured."""
        settings_copy = dict(drf_stripe_settings.user_settings)
        settings_copy['BILLING_ACCOUNT_MODEL'] = 'tests.Company'
        return settings_copy

    def test_webhook_subscription_created_links_to_billing_account(self):
        """
        Test that webhook subscription created event links subscription to billing account
        when BILLING_ACCOUNT_MODEL is configured.
        """
        with override_settings(DRF_STRIPE=self.get_billing_settings()):
            drf_stripe_settings.reload()

            event = self._load_test_data("2020-08-27/webhook_subscription_created.json")
            handle_webhook_event(event)

            # Check subscription was created and linked to billing account
            subscription = Subscription.objects.get(subscription_id="sub_1KHlYHL14ex1CGCiIBo8Xk5p")
            self.assertEqual(subscription.stripe_user.customer_id, "cus_tester")

            # Check billing account content type and object id are set
            company_ct = ContentType.objects.get_for_model(Company)
            self.assertEqual(subscription.billing_account_content_type, company_ct)
            self.assertEqual(subscription.billing_account_object_id, self.company.pk)

            # Check billing account fields are updated
            self.company.refresh_from_db()
            self.assertEqual(self.company.stripe_customer_id, "cus_tester")
            self.assertEqual(self.company.stripe_subscription_id, "sub_1KHlYHL14ex1CGCiIBo8Xk5p")

            drf_stripe_settings.reload()

    def test_webhook_subscription_without_billing_model_works_as_before(self):
        """
        Test that webhook works as before when BILLING_ACCOUNT_MODEL is not configured.
        """
        event = self._load_test_data("2020-08-27/webhook_subscription_created.json")
        handle_webhook_event(event)

        # Check subscription was created
        subscription = Subscription.objects.get(subscription_id="sub_1KHlYHL14ex1CGCiIBo8Xk5p")
        self.assertEqual(subscription.stripe_user.customer_id, "cus_tester")

        # Check billing account fields are NOT set (legacy behavior)
        self.assertIsNone(subscription.billing_account_content_type)
        self.assertIsNone(subscription.billing_account_object_id)

        # Company should not be updated
        self.company.refresh_from_db()
        self.assertIsNone(self.company.stripe_customer_id)
        self.assertIsNone(self.company.stripe_subscription_id)
