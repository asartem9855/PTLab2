"""Input validation for a purchase without an account."""
from django import forms

from .models import validate_birth_date


class PurchaseForm(forms.Form):
    person = forms.CharField(label="Получатель", max_length=200)
    birth_date = forms.DateField(
        label="Дата рождения", validators=[validate_birth_date],
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="В день рождения действует скидка 10%.",
    )
    address = forms.CharField(
        label="Адрес доставки", max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    quantity = forms.IntegerField(
        label="Количество", min_value=1, max_value=99, initial=1
    )
