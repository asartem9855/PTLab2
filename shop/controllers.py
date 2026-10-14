"""MVC Controller: HTTP requests -> model operations -> HTML views."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET

from .forms import PurchaseForm, RegistrationForm
from .models import Customer, Product, Purchase, birthday_discount


def get_customer(request):
    if not request.user.is_authenticated:
        return None
    return Customer.objects.filter(user=request.user).first()


@require_GET
def index(request):
    customer = get_customer(request)
    birth_date = customer.birth_date if customer else None
    products = Product.objects.filter(active=True)
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(name__icontains=query)
    cards = [{"product": product, "quote": product.quote(birth_date)}
             for product in products]
    return render(request, "shop/index.html", {
        "cards": cards, "query": query,
        "birthday": birthday_discount(birth_date, timezone.localdate()) == 10,
    })


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Аккаунт создан. Добро пожаловать!")
        return redirect("index")
    return render(request, "registration/register.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def buy(request, product_id):
    product = get_object_or_404(Product, pk=product_id, active=True)
    customer = get_customer(request)
    if customer is None:
        return render(request, "shop/profile_required.html", status=403)
    form = PurchaseForm(
        request.POST or None, initial={"person": str(customer)}
    )
    quantity = 1
    if request.method == "POST" and form.is_valid():
        quantity = form.cleaned_data["quantity"]
        if "confirm" in request.POST:
            try:
                purchase = Purchase.place(
                    product=product, customer=customer, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return redirect("receipt", purchase_id=purchase.pk)
    return render(request, "shop/purchase_form.html", {
        "product": product, "form": form,
        "quote": product.quote(customer.birth_date, quantity),
    })


@login_required
@require_GET
def orders(request):
    purchases = Purchase.objects.filter(
        customer__user=request.user
    ).select_related("product")
    return render(request, "shop/orders.html", {"purchases": purchases})


@login_required
@require_GET
def receipt(request, purchase_id):
    purchase = get_object_or_404(
        Purchase.objects.select_related("product"), pk=purchase_id,
        customer__user=request.user,
    )
    return render(request, "shop/receipt.html", {"purchase": purchase})


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})
