"""Input validation shared by the MVC controllers."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import Customer, validate_birth_date


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    birth_date = forms.DateField(
        label="Дата рождения", validators=[validate_birth_date],
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="В день рождения скидка 10% применяется автоматически.",
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "birth_date", "password1",
                  "password2")

    @transaction.atomic
    def save(self):
        user = super().save()
        Customer.objects.create(user=user, birth_date=self.cleaned_data[
            "birth_date"
        ])
        return user


class PurchaseForm(forms.Form):
    person = forms.CharField(label="Получатель", max_length=200)
    address = forms.CharField(
        label="Адрес доставки", max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    quantity = forms.IntegerField(
        label="Количество", min_value=1, max_value=99, initial=1
    )
