"""
Test that the DEFAULT_SUBSCRIPTION_QUANTITY setting works correctly for subscription quantities.
"""
from django.test import TestCase, override_settings
from drf_stripe.settings import drf_stripe_settings
from drf_stripe.models import AbstractBillingAccount, get_drf_stripe_user_model


class TestBillingAccountSeats(TestCase):
    """Test DEFAULT_SUBSCRIPTION_QUANTITY setting behavior for subscription quantities."""

    def test_default_subscription_quantity_setting_exists(self):
        """Verify the DEFAULT_SUBSCRIPTION_QUANTITY setting is accessible."""
        self.assertEqual(drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY, 1)

    @override_settings(DRF_STRIPE={"DEFAULT_SUBSCRIPTION_QUANTITY": 5})
    def test_default_subscription_quantity_can_be_overridden(self):
        """Verify the DEFAULT_SUBSCRIPTION_QUANTITY setting can be overridden."""
        # Need to reload settings after override
        drf_stripe_settings.reload()
        self.assertEqual(drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY, 5)
        # Reload again to restore default
        drf_stripe_settings.reload()

    def test_getattr_fallback_to_setting(self):
        """Test that getattr uses the setting as fallback when seats doesn't exist."""
        
        class MockBillingAccountWithoutSeats:
            """Mock billing account without seats field."""
            pass
        
        instance = MockBillingAccountWithoutSeats()
        quantity = getattr(instance, "seats", drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY)
        self.assertEqual(quantity, 1)


class TestAbstractBillingAccountFields(TestCase):
    """Test that AbstractBillingAccount has correct fields after refactoring."""

    def test_abstract_billing_account_does_not_have_seats_field(self):
        """Verify that seats field is not in AbstractBillingAccount."""
        fields = [f.name for f in AbstractBillingAccount._meta.get_fields()]
        self.assertNotIn('seats', fields)
    
    def test_abstract_billing_account_has_required_fields(self):
        """Verify that AbstractBillingAccount has the required fields."""
        fields = [f.name for f in AbstractBillingAccount._meta.get_fields()]
        self.assertIn('stripe_customer_id', fields)
        self.assertIn('stripe_subscription_id', fields)
        self.assertIn('manager_user', fields)
    
    def test_abstract_billing_account_is_abstract(self):
        """Verify that AbstractBillingAccount is an abstract model."""
        self.assertTrue(AbstractBillingAccount._meta.abstract)
