from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shop.models import Product, Purchase


@override_settings(STORAGES={
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
})
class ControllerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(name="Ручка", price="120.00")
        cls.hidden = Product.objects.create(
            name="Архив", price="50.00", active=False
        )

    def setUp(self):
        self.buy_url = reverse("buy", args=[self.product.pk])
        self.data = {"person": "Иван", "address": "Университет, 1",
                     "birth_date": "2000-10-14", "quantity": 2, "confirm": "1"}

    def test_catalog(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Ручка")
        self.assertNotContains(response, "Архив")
        self.assertNotContains(response, "<img")
        self.assertContains(response, "120,00")
        Product.objects.all().update(active=False)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Товары не найдены")
        self.assertEqual(self.client.post(reverse("index")).status_code, 405)

    def test_purchase_without_account(self):
        response = self.client.get(self.buy_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="birth_date"')
        for url in ["/register/", "/login/", "/logout/", "/orders/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 14))
    def test_order_ignores_price_tampering(self, _):
        self.data.update(total_price="0.01", discount_percent="100",
                         product=self.hidden.pk)
        response = self.client.post(self.buy_url, self.data)
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total_price, Decimal("216.00"))
        self.assertEqual(purchase.product, self.product)
        self.assertEqual(purchase.birth_date, date(2000, 10, 14))
        self.assertRedirects(response, reverse("receipt", args=[purchase.pk]))
        self.assertContains(self.client.get(response.url), "216,00")
        self.client.get(response.url)
        self.assertEqual(Purchase.objects.count(), 1)

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 14))
    def test_preview_does_not_create_order(self, _):
        self.data.pop("confirm")
        response = self.client.post(self.buy_url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["quote"]["total"], Decimal("216"))
        self.assertFalse(Purchase.objects.exists())

    @patch("shop.models.timezone.localdate", return_value=date(2026, 10, 15))
    def test_regular_purchase(self, _):
        self.client.post(self.buy_url, self.data)
        self.assertEqual(Purchase.objects.get().total_price, Decimal("240"))

    def test_invalid_form_and_product(self):
        for change in [
            {"quantity": 0}, {"quantity": 100}, {"person": " "},
            {"address": ""}, {"quantity": "abc"}, {"birth_date": ""},
            {"birth_date": "not-date"}, {"birth_date": "1899-01-01"},
            {"birth_date": str(timezone.localdate() + timedelta(days=1))},
        ]:
            with self.subTest(change=change):
                response = self.client.post(self.buy_url, self.data | change)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertTrue(self.client.post(
            self.buy_url, {}
        ).context["form"].errors)
        self.assertFalse(Purchase.objects.exists())
        for pk in [self.hidden.pk, 99999]:
            self.assertEqual(self.client.get(
                reverse("buy", args=[pk])
            ).status_code, 404)

    @patch("shop.controllers.Purchase.place",
           side_effect=ValidationError("Товар больше не продаётся"))
    def test_purchase_error_is_shown(self, _):
        response = self.client.post(self.buy_url, self.data)
        self.assertContains(response, "Товар больше не продаётся")

    def test_receipts_are_private_and_escaped(self):
        self.data["person"] = "<script>alert(1)</script>"
        self.client.post(self.buy_url, self.data)
        order = Purchase.objects.get()
        url = reverse("receipt", args=[order.pk])
        response = self.client.get(url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")
        self.assertEqual(Client().get(url).status_code, 404)
        self.client.post(self.buy_url, self.data)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.buy_url, self.data).status_code, 403)
        client.get(self.buy_url)
        self.data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.buy_url, self.data).status_code, 302)

    def test_health_and_admin_permissions(self):
        self.assertEqual(self.client.get(reverse("health")).json(),
                         {"status": "ok"})
        self.assertEqual(self.client.get(reverse("admin:index")).status_code,
                         302)
        admin = User.objects.create_superuser("admin", password="Admin!Test42")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code,
                         200)
        self.assertEqual(self.client.get(
            reverse("admin:shop_purchase_add")
        ).status_code, 403)
        self.assertEqual(self.client.get(
            reverse("admin:shop_purchase_delete", args=[999])
        ).status_code, 403)
