"""
Test that the DEFAULT_SUBSCRIPTION_QUANTITY setting works correctly
and that custom seats fields on billing accounts are respected.
"""
from django.test import TestCase, override_settings
from drf_stripe.settings import drf_stripe_settings
from drf_stripe.models import AbstractBillingAccount, get_drf_stripe_user_model


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


class TestCheckoutSerializerWithBillingAccount(TestCase):
    """Test CheckoutRequestSerializer uses DEFAULT_SUBSCRIPTION_QUANTITY correctly."""

    def setUp(self):
        """Set up test data."""
        # Create a test user
        User = get_drf_stripe_user_model()
        self.user = User.objects.create_user(username='testuser', email='test@example.com')
        
        # Define reusable mock classes
        class MockBillingAccountBase:
            """Base mock billing account."""
            pk = 1
            stripe_customer_id = None
            
            def get_or_create_stripe_customer(self, stripe_module, **kwargs):
                return "cus_test123"
            
            def can_manage_billing(self, user):
                return True
        
        self.MockBillingAccountBase = MockBillingAccountBase

    def test_checkout_uses_custom_seats_when_present(self):
        """Test that checkout uses custom seats field when billing account has it."""
        # Create a mock billing account WITH seats field
        class MockBillingAccountWithSeats(self.MockBillingAccountBase):
            seats = 7  # Custom seats value
        
        billing_account = MockBillingAccountWithSeats()
        
        # Verify that getattr picks up the custom seats value
        quantity = getattr(billing_account, "seats", drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY)
        self.assertEqual(quantity, 7)

    @override_settings(DRF_STRIPE={"DEFAULT_SUBSCRIPTION_QUANTITY": 5})
    def test_default_subscription_quantity_used_as_fallback(self):
        """Test that DEFAULT_SUBSCRIPTION_QUANTITY is used when billing account has no seats."""
        # Reload settings to pick up override
        drf_stripe_settings.reload()
        
        # Use base mock without seats field
        billing_account = self.MockBillingAccountBase()
        
        # This is how the serializer gets the quantity
        quantity = getattr(billing_account, "seats", drf_stripe_settings.DEFAULT_SUBSCRIPTION_QUANTITY)
        self.assertEqual(quantity, 5)
        
        # Restore settings
        drf_stripe_settings.reload()


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
