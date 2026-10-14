from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shop.models import Customer, Product, Purchase


@override_settings(STORAGES={
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
})
class ControllerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("buyer", password="Strong!Test42")
        cls.customer = Customer.objects.create(
            user=cls.user, birth_date=date(2000, 10, 14)
        )
        cls.product = Product.objects.create(name="Ручка", price="120.00")
        cls.hidden = Product.objects.create(
            name="Архив", price="50.00", active=False
        )

    def setUp(self):
        self.buy_url = reverse("buy", args=[self.product.pk])
        self.data = {"person": "Иван", "address": "Университет, 1",
                     "quantity": 2, "confirm": "1"}

    def test_catalog_and_search(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Ручка")
        self.assertNotContains(response, "Архив")
        response = self.client.get(reverse("index"), {"q": "Нет такого"})
        self.assertContains(response, "Товары не найдены")
        self.assertEqual(self.client.post(reverse("index")).status_code, 405)

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 14))
    def test_birthday_prices_in_catalog(self, _):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "108,00")
        self.assertTrue(response.context["birthday"])

    def test_anonymous_purchase_redirects_to_login(self):
        self.assertRedirects(
            self.client.get(self.buy_url),
            reverse("login") + "?next=" + self.buy_url,
        )

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 14))
    def test_order_ignores_price_and_date_tampering(self, _):
        self.client.force_login(self.user)
        self.data.update(total_price="0.01", discount_percent="100",
                         birth_date="1900-01-01", product=self.hidden.pk)
        response = self.client.post(self.buy_url, self.data)
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total_price, Decimal("216.00"))
        self.assertEqual(purchase.product, self.product)
        self.assertRedirects(response, reverse("receipt", args=[purchase.pk]))
        self.assertContains(self.client.get(response.url), "216,00")

    def test_preview_does_not_create_order(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.buy_url).status_code, 200)
        self.data.pop("confirm")
        response = self.client.post(self.buy_url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["quote"]["subtotal"], Decimal("240"))
        self.assertFalse(Purchase.objects.exists())

    def test_invalid_form_and_product(self):
        self.client.force_login(self.user)
        for change in [{"quantity": 0}, {"quantity": 100}, {"person": " "},
                       {"address": ""}, {"quantity": "abc"}]:
            with self.subTest(change=change):
                response = self.client.post(self.buy_url, self.data | change)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(Purchase.objects.exists())
        for pk in [self.hidden.pk, 99999]:
            self.assertEqual(self.client.get(
                reverse("buy", args=[pk])
            ).status_code, 404)

    @patch("shop.controllers.Purchase.place",
           side_effect=ValidationError("Товар больше не продаётся"))
    def test_purchase_error_is_shown(self, _):
        self.client.force_login(self.user)
        response = self.client.post(self.buy_url, self.data)
        self.assertContains(response, "Товар больше не продаётся")

    def test_orders_are_private_and_escaped(self):
        self.client.force_login(self.user)
        self.data["person"] = "<script>alert(1)</script>"
        self.client.post(self.buy_url, self.data)
        order = Purchase.objects.get()
        response = self.client.get(reverse("receipt", args=[order.pk]))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")
        self.assertContains(self.client.get(reverse("orders")), "Ручка")
        other = User.objects.create_user("other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(
            reverse("receipt", args=[order.pk])
        ).status_code, 404)
        self.assertContains(self.client.get(reverse("orders")),
                            "Здесь появятся ваши заказы")

    def test_user_without_customer_profile(self):
        user = User.objects.create_user("no-profile")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.buy_url).status_code, 403)
        self.assertEqual(self.client.get(reverse("index")).status_code, 200)

    def registration_data(self):
        return {"username": "newbuyer", "first_name": "Анна",
                "birth_date": "2000-05-15", "password1": "Strong!Test42",
                "password2": "Strong!Test42"}

    def test_registration_creates_profile_and_login(self):
        self.assertEqual(self.client.get(reverse("register")).status_code, 200)
        response = self.client.post(reverse("register"),
                                    self.registration_data())
        self.assertRedirects(response, reverse("index"))
        user = User.objects.get(username="newbuyer")
        self.assertTrue(user.check_password("Strong!Test42"))
        self.assertEqual(user.customer.birth_date, date(2000, 5, 15))
        self.assertRedirects(self.client.get(reverse("register")),
                             reverse("index"))

    def test_registration_validation(self):
        for change in [
            {"birth_date": str(timezone.localdate() + timedelta(days=1))},
            {"birth_date": "1899-01-01"}, {"birth_date": "not-date"},
            {"username": "buyer"}, {"password2": "different"},
        ]:
            with self.subTest(change=change):
                response = self.client.post(
                    reverse("register"), self.registration_data() | change
                )
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="newbuyer").exists())

    def test_login_logout_and_csrf(self):
        response = self.client.post(reverse("login"), {
            "username": "buyer", "password": "Strong!Test42",
        })
        self.assertRedirects(response, reverse("index"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")),
                             reverse("index"))
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.buy_url, self.data).status_code, 403)

    def test_health_and_admin_permissions(self):
        self.assertEqual(self.client.get(reverse("health")).json(),
                         {"status": "ok"})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code,
                         302)
        admin = User.objects.create_superuser("admin", password="Admin!Test42")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code,
                         200)
        self.assertEqual(self.client.get(
            reverse("admin:shop_purchase_add")
        ).status_code, 403)
