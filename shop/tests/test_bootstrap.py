import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase

from shop.models import Customer, Product


class BootstrapTests(TestCase):
    def run_command(self):
        call_command("bootstrap_demo", stdout=StringIO())

    @patch.dict(os.environ, {
        "DJANGO_SUPERUSER_USERNAME": "admin",
        "DJANGO_SUPERUSER_PASSWORD": "Admin!Test42",
        "DEMO_CUSTOMER_PASSWORD": "Demo!Test42",
    })
    def test_idempotent_and_no_password_reset(self):
        self.run_command()
        admin = User.objects.get(username="admin")
        admin.set_password("Changed!Password42")
        admin.save()
        self.run_command()
        admin.refresh_from_db()
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("Changed!Password42"))
        self.assertEqual(Product.objects.count(), 6)
        self.assertEqual(Customer.objects.count(), 1)

    @patch.dict(os.environ, {
        "DJANGO_SUPERUSER_USERNAME": "existing",
        "DJANGO_SUPERUSER_PASSWORD": "Test!42",
    })
    def test_does_not_elevate_existing_account(self):
        User.objects.create_user("existing")
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertFalse(User.objects.get(username="existing").is_superuser)

    @patch.dict(os.environ, {
        "DJANGO_SUPERUSER_USERNAME": "admin", "DJANGO_SUPERUSER_PASSWORD": "",
    })
    def test_password_required_for_new_admin(self):
        with self.assertRaises(CommandError):
            self.run_command()

    @patch.dict(os.environ, {
        "DJANGO_SUPERUSER_USERNAME": "", "DEMO_CUSTOMER_PASSWORD": "",
    })
    def test_catalog_only(self):
        self.run_command()
        self.assertEqual(Product.objects.count(), 6)
        self.assertFalse(User.objects.exists())
