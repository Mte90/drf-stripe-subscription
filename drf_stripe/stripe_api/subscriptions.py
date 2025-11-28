from itertools import chain
from operator import attrgetter
from typing import Literal, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models import QuerySet
from django.db.transaction import atomic

from drf_stripe.stripe_api.api import stripe_api as stripe
from .customers import get_or_create_stripe_user, CreatingNewUsersDisabledError, get_billing_model, find_billing_account
from ..models import Subscription, Price, SubscriptionItem
from ..stripe_models.subscription import ACCESS_GRANTING_STATUSES, StripeSubscriptions

"""
status argument, see https://stripe.com/docs/api/subscriptions/list?lang=python#list_subscriptions-status
"""
STATUS_ARG = Literal[
    "active",
    "past_due",
    "unpaid",
    "canceled",
    "incomplete",
    "incomplete_expired",
    "trialing",
    "all",
    "ended"
]


@atomic
def stripe_api_update_subscriptions(status: STATUS_ARG = None, limit: int = 100, starting_after: str = None,
                                    test_data=None, ignore_new_user_creation_errors = False):
    """
    Retrieve all subscriptions. Updates database.

    Called from management command.

    When BILLING_ACCOUNT_MODEL is configured, this function will also:
    - Find the billing account by stripe_customer_id or by manager_user
    - Update the billing account's stripe_customer_id and stripe_subscription_id fields
    - Link the subscription to the billing account via billing_account_content_type and billing_account_object_id

    :param STATUS_ARG status: subscription status to retrieve.
    :param int limit: number of instances to retrieve( between 0 and 100).
    :param str starting_after: subscription id to start retrieving.
    :param test_data: response data from Stripe API stripe.Subscription.list, used for testing
    :param ignore_new_user_creation_errors: if True, CreatingNewUsersDisabledError thrown by get_or_create_stripe_user() will be skipped
    """

    if limit < 0 or limit > 100:
        raise ValueError("Argument limit should be a positive integer no greater than 100.")

    if test_data is None:
        subscriptions_response = stripe.Subscription.list(status=status, limit=limit, starting_after=starting_after)
    else:
        subscriptions_response = test_data

    stripe_subscriptions = StripeSubscriptions(**subscriptions_response).data

    billing_model = get_billing_model()

    creation_count = 0

    for subscription in stripe_subscriptions:
        try:
            stripe_user = get_or_create_stripe_user(customer_id=subscription.customer)

            subscription_defaults = {
                "stripe_user": stripe_user,
                "period_start": subscription.current_period_start,
                "period_end": subscription.current_period_end,
                "cancel_at": subscription.cancel_at,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "ended_at": subscription.ended_at,
                "status": subscription.status,
                "trial_end": subscription.trial_end,
                "trial_start": subscription.trial_start
            }

            # Link to billing account if configured
            if billing_model:
                user = stripe_user.user if stripe_user else None
                billing_account = find_billing_account(billing_model, customer_id=subscription.customer, user=user)

                if billing_account:
                    # Update billing account stripe fields
                    update_fields = []
                    if not billing_account.stripe_customer_id:
                        billing_account.stripe_customer_id = subscription.customer
                        update_fields.append("stripe_customer_id")
                    if billing_account.stripe_subscription_id != subscription.id:
                        billing_account.stripe_subscription_id = subscription.id
                        update_fields.append("stripe_subscription_id")
                    if update_fields:
                        billing_account.save(update_fields=update_fields)
                        print(f"Updated billing account {billing_account.pk} with stripe fields")

                    # Link subscription to billing account
                    subscription_defaults["billing_account_content_type"] = ContentType.objects.get_for_model(billing_model)
                    subscription_defaults["billing_account_object_id"] = billing_account.pk

            _, created = Subscription.objects.update_or_create(
                subscription_id=subscription.id,
                defaults=subscription_defaults
            )
            print(f"Updated subscription {subscription.id}")
            _update_subscription_items(subscription.id, subscription.items.data)
            if created is True:
                creation_count += 1
        except CreatingNewUsersDisabledError as e:
            if not ignore_new_user_creation_errors:
                raise e
            else:
                print(f"User for customer id '{subscription.customer}' with subscription '{subscription.id}' does not exist, skipping.")

    print(f"Created {creation_count} new Subscriptions.")


def _update_subscription_items(subscription_id, items_data):
    SubscriptionItem.objects.filter(subscription=subscription_id).delete()
    for item in items_data:
        _, created = SubscriptionItem.objects.update_or_create(
            sub_item_id=item.id,
            defaults={
                "subscription_id": subscription_id,
                "price_id": item.price.id,
                "quantity": item.quantity
            }
        )
        print(f"Updated sub item {item.id}")


# def _stripe_api_update_subscription_items(subscription_id, limit=100, ending_before=None, test_data=None):
#     """
#     param: str subscription_id: subscription id for which to retrieve subscription items
#     :param int limit: number of instances to retrieve( between 0 and 100).
#     :param str ending_before: subscription item id to retrieve before.
#     """
#     if limit < 0 or limit > 100:
#         raise ValueError("Argument limit should be a positive integer no greater than 100.")
#
#     if test_data is None:
#         items_response = stripe.SubscriptionItem.list(subscription=subscription_id,
#                                                       limit=limit,
#                                                       ending_before=ending_before)
#     else:
#         items_response = test_data
#
#     sub_items = StripeSubscriptionItems(**items_response).data
#
#     SubscriptionItem.objects.filter(subscription=subscription_id).delete()
#     for item in sub_items:
#         SubscriptionItem.objects.update_or_create(
#             sub_item_id=item.id,
#             defaults={
#                 "subscription_id": subscription_id,
#                 "price_id": item.price.id,
#                 "quantity": item.quantity
#             }
#         )


def list_user_subscriptions(user_id, current=True) -> QuerySet[Subscription]:
    """
    Retrieve a set of Subscriptions associated with a given user id.

    :param user_id: Django User id.
    :param bool current: Defaults to True and retrieves only current subscriptions
        (excluding any cancelled, ended, unpaid subscriptions)
    """
    q = Q(stripe_user__user_id=user_id)
    if current is True:
        q &= Q(status__in=ACCESS_GRANTING_STATUSES)

    return Subscription.objects.filter(q)


def list_user_subscription_items(user_id, current=True) -> QuerySet[SubscriptionItem]:
    """
    Retrieve a set of SubscriptionItems associated with user id

    :param user_id: Django User is.
    :param bool current: Defaults to True and retrieves only current subscriptions
        (excluding any cancelled, ended, unpaid subscriptions)
    """
    q = Q(subscription__stripe_user__user_id=user_id)
    if current is True:
        q &= Q(subscription__status__in=ACCESS_GRANTING_STATUSES)

    return SubscriptionItem.objects.filter(q)


def list_user_subscription_products(user_id, current=True):
    """
    Retrieve a set of Product instances associated with a given User instance.

    :param user_id: Django User id.
    :param bool current: Defaults to True and retrieves only products associated with current subscriptions
        (excluding any cancelled, ended, unpaid subscription products)
    """
    subscriptions = list_user_subscriptions(user_id, current=current)
    sub_items = chain.from_iterable(
        sub.items.all() for sub in subscriptions.all().prefetch_related("items__price__product"))
    products = set(item.price.product for item in sub_items)
    return products


def list_subscribable_product_prices_to_user(user_id):
    """
    Retrieve a set of Price instances associated with Products that the User isn't currently subscribed to.

    :param user_id: Django user id.
    """
    current_products = set(map(attrgetter('product_id'), list_user_subscription_products(user_id)))
    prices = Price.objects.filter(
        Q(active=True) &
        Q(product__active=True) &
        ~Q(product__product_id__in=current_products)
    )
    return prices


def list_all_available_product_prices(expand: List = None):
    """Retrieve a set of all Price instances that are available to public."""

    prices = Price.objects.filter(Q(active=True) & Q(product__active=True))

    if expand and "feature" in expand:
        prices = prices.prefetch_related("product__linked_features__feature")

    return prices
