"""
Test that the DEFAULT_SUBSCRIPTION_QUANTITY setting works correctly
and that custom seats fields on billing accounts are respected.
"""
from django.test import TestCase, override_settings
from drf_stripe.settings import drf_stripe_settings


class TestBillingAccountSeats(TestCase):
    """Test seats/quantity behavior with new DEFAULT_SUBSCRIPTION_QUANTITY setting."""

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

    def test_getattr_uses_custom_seats_when_present(self):
        """Test that getattr uses custom seats field when it exists."""
        
        class MockBillingAccountWithSeats:
            """Mock billing account with seats field."""
            seats = 10
        
        instance = MockBillingAccountWithSeats()
        quantity = getattr(instance, "seats", drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY)
        self.assertEqual(quantity, 10)
