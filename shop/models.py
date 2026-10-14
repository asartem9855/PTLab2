"""MVC Model: persisted entities and the birthday pricing rule."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def validate_birth_date(value):
    if value > timezone.localdate():
        raise ValidationError("Дата рождения не может быть в будущем.")
    if value < date(1900, 1, 1):
        raise ValidationError("Укажите дату рождения не ранее 1900 года.")


def birthday_discount(birth_date, on_date):
    """Exactly matching month/day; February 29 only in leap years."""
    if birth_date and (birth_date.month, birth_date.day) == (
        on_date.month, on_date.day
    ):
        return 10
    return 0


class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="customer", verbose_name="Пользователь",
    )
    birth_date = models.DateField(
        "Дата рождения", validators=[validate_birth_date]
    )

    class Meta:
        verbose_name = "Покупатель"
        verbose_name_plural = "Покупатели"

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Product(models.Model):
    name = models.CharField("Название", max_length=200)
    price = models.DecimalField(
        "Цена, ₽", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.TextField("Описание", blank=True)
    category = models.CharField(
        "Категория", max_length=80, default="Канцтовары"
    )
    active = models.BooleanField("В продаже", default=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        constraints = [models.CheckConstraint(
            condition=models.Q(price__gt=0), name="product_price_positive"
        )]

    def __str__(self):
        return self.name

    def quote(self, birth_date=None, quantity=1, on_date=None):
        if type(quantity) is not int or not 1 <= quantity <= 99:
            raise ValidationError("Количество должно быть от 1 до 99.")
        on_date = on_date or timezone.localdate()
        discount = birthday_discount(birth_date, on_date)
        subtotal = (self.price * quantity).quantize(Decimal("0.01"))
        total = (subtotal * (100 - discount) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return {"subtotal": subtotal, "discount_percent": discount,
                "discount_amount": subtotal - total, "total": total}


class Purchase(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, verbose_name="Товар"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name="Покупатель",
    )
    person = models.CharField("Получатель", max_length=200)
    address = models.CharField("Адрес доставки", max_length=200)
    date = models.DateTimeField("Создан", auto_now_add=True)
    quantity = models.PositiveSmallIntegerField(
        "Количество", default=1,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
    )
    birth_date = models.DateField("Дата рождения на момент покупки", null=True)
    unit_price = models.DecimalField(
        "Цена за единицу", max_digits=10, decimal_places=2, default=0
    )
    discount_percent = models.PositiveSmallIntegerField("Скидка, %", default=0)
    total_price = models.DecimalField(
        "Итого, ₽", max_digits=12, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=99),
                name="purchase_quantity_range",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_percent__in=[0, 10]),
                name="purchase_valid_discount",
            ),
        ]

    def __str__(self):
        return f"Заказ № {self.pk} — {self.person}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def discount_amount(self):
        return self.subtotal - self.total_price

    @classmethod
    @transaction.atomic
    def place(cls, *, product, customer, person, address, quantity):
        product = Product.objects.select_for_update().get(pk=product.pk)
        if not product.active:
            raise ValidationError("Этот товар больше не продаётся.")
        customer.full_clean()
        quote = product.quote(customer.birth_date, quantity)
        purchase = cls(
            product=product, customer=customer, person=person, address=address,
            quantity=quantity, birth_date=customer.birth_date,
            unit_price=product.price,
            discount_percent=quote["discount_percent"],
            total_price=quote["total"],
        )
        purchase.full_clean()
        purchase.save()
        return purchase
