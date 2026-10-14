"""Idempotent catalog/admin initialization; secrets are never printed."""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from shop.models import Customer, Product

CATALOG = [
    ("Блокнот «Идеи»", "Блокноты", "390.00",
     "80 листов в точку, мягкая обложка и место для новых идей."),
    ("Ручка гелевая", "Письмо", "120.00",
     "Тонкая линия 0,5 мм. Чёрные чернила для ясных мыслей."),
    ("Карандаши, набор 12 шт.", "Рисование", "480.00",
     "Двенадцать спокойных оттенков для ярких открытий."),
    ("Тетрадь А5, 96 листов", "Тетради", "185.50",
     "Плотная бумага в клетку. Для лекций, заметок и планов."),
    ("Маркеры, набор 4 шт.", "Письмо", "299.90",
     "Пастельные текстовыделители — главное всегда на виду."),
    ("Папка для документов", "Хранение", "210.00",
     "Формат А4, надёжная застёжка и порядок в документах."),
]


class Command(BaseCommand):
    help = "Create demo catalog and optional admin/customer from environment"

    @transaction.atomic
    def handle(self, *args, **options):
        for name, category, price, description in CATALOG:
            Product.objects.get_or_create(name=name, defaults={
                "category": category, "price": price,
                "description": description,
            })
        User = get_user_model()
        admin_name = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        admin_password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if admin_name:
            user = User.objects.filter(username=admin_name).first()
            if user and not user.is_superuser:
                raise CommandError("Existing account is not a superuser")
            if user is None:
                if not admin_password:
                    raise CommandError("Set DJANGO_SUPERUSER_PASSWORD")
                User.objects.create_superuser(
                    username=admin_name, password=admin_password,
                    email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
                )
        demo_password = os.environ.get("DEMO_CUSTOMER_PASSWORD")
        if demo_password:
            user, created = User.objects.get_or_create(
                username="birthday_demo", defaults={"first_name": "Именинник"}
            )
            if created:
                user.set_password(demo_password)
                user.save()
                today = timezone.localdate()
                Customer.objects.create(
                    user=user, birth_date=today.replace(year=2000)
                )
        self.stdout.write(self.style.SUCCESS("Catalog and accounts are ready"))
