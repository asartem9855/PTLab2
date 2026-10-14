from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from shop.models import (Customer, Product, Purchase, birthday_discount,
                         validate_birth_date)


class BirthdayRuleTests(SimpleTestCase):
    def test_calendar_boundaries(self):
        cases = [
            (date(2000, 10, 14), date(2026, 10, 14), 10),
            (date(2000, 10, 14), date(2026, 10, 13), 0),
            (date(2000, 10, 14), date(2026, 10, 15), 0),
            (date(2000, 10, 14), date(2026, 9, 14), 0),
            (date(2000, 1, 1), date(2026, 1, 1), 10),
            (date(2000, 12, 31), date(2026, 12, 31), 10),
            (date(2000, 2, 29), date(2028, 2, 29), 10),
            (date(2000, 2, 29), date(2027, 2, 28), 0),
            (date(2000, 2, 29), date(2027, 3, 1), 0),
            (None, date(2026, 10, 14), 0),
        ]
        for born, today, expected in cases:
            with self.subTest(born=born, today=today):
                self.assertEqual(birthday_discount(born, today), expected)

    def test_birth_date_validation(self):
        for invalid in [timezone.localdate() + timedelta(days=1),
                        date(1899, 12, 31)]:
            with self.subTest(invalid=invalid), self.assertRaises(
                ValidationError
            ):
                validate_birth_date(invalid)
        validate_birth_date(date(1900, 1, 1))
        validate_birth_date(timezone.localdate())

    def test_price_and_rounding(self):
        product = Product(price=Decimal("10.05"))
        quote = product.quote(date(2000, 1, 1), 1, date(2026, 1, 1))
        self.assertEqual(quote["total"], Decimal("9.05"))
        self.assertEqual(quote["discount_amount"], Decimal("1.00"))
        self.assertEqual(product.quote(quantity=3)["total"], Decimal("30.15"))

    def test_all_quantities_and_no_float(self):
        for quantity in [0, -1, 100, True, 1.5, "2"]:
            with self.subTest(quantity=quantity), self.assertRaises(
                ValidationError
            ):
                Product(price=Decimal("120")).quote(quantity=quantity)
        self.assertEqual(Product(price=Decimal("120")).quote(
            date(2000, 1, 1), 99, date(2026, 1, 1)
        )["total"], Decimal("10692.00"))


class PurchaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer")
        self.customer = Customer.objects.create(
            user=self.user, birth_date=date(2000, 10, 14)
        )
        self.product = Product.objects.create(
            name="Ручка", price=Decimal("120.00")
        )

    def place(self, **kwargs):
        data = dict(product=self.product, customer=self.customer,
                    person="Иван", address="Университет, 1", quantity=2)
        data.update(kwargs)
        return Purchase.place(**data)

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 14))
    def test_birthday_snapshot(self, _):
        order = self.place()
        self.assertEqual(order.total_price, Decimal("216.00"))
        self.assertEqual(order.discount_percent, 10)
        self.assertEqual(order.subtotal, Decimal("240.00"))
        self.assertEqual(order.discount_amount, Decimal("24.00"))
        self.product.price = Decimal("999.00")
        self.product.save()
        self.customer.birth_date = date(2001, 5, 5)
        self.customer.save()
        order.refresh_from_db()
        self.assertEqual(order.unit_price, Decimal("120.00"))
        self.assertEqual(order.total_price, Decimal("216.00"))
        self.assertEqual(order.birth_date, date(2000, 10, 14))
        self.assertIn("Иван", str(order))

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 15))
    def test_regular_purchase(self, _):
        self.assertEqual(self.place().total_price, Decimal("240.00"))

    def test_inactive_product(self):
        self.product.active = False
        self.product.save()
        with self.assertRaises(ValidationError):
            self.place()
        self.assertEqual(Purchase.objects.count(), 0)

    def test_invalid_order_is_not_saved(self):
        for override in [{"quantity": 0}, {"person": ""}, {"address": ""}]:
            with self.subTest(override=override), self.assertRaises(
                ValidationError
            ):
                self.place(**override)
        self.assertEqual(Purchase.objects.count(), 0)

    def test_protect_purchased_product_and_customer(self):
        self.place()
        for entity in [self.product, self.customer]:
            with self.assertRaises(ProtectedError):
                entity.delete()

    def test_current_database_price_is_used(self):
        Product.objects.filter(pk=self.product.pk).update(price="200.00")
        self.assertEqual(self.place().unit_price, Decimal("200.00"))

    def test_model_names(self):
        self.assertEqual(str(self.product), "Ручка")
        self.assertEqual(str(self.customer), "buyer")
        self.user.first_name = "Анна"
        self.assertEqual(str(self.customer), "Анна")

    def test_invalid_price_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(name="Ошибка", price=0)
