"""MVC Controller: HTTP requests -> model operations -> HTML views."""
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_GET

from .forms import PurchaseForm
from .models import Product, Purchase


@require_GET
def index(request):
    products = Product.objects.filter(active=True)
    return render(request, "shop/index.html", {
        "products": products,
    })


@require_http_methods(["GET", "POST"])
def buy(request, product_id):
    product = get_object_or_404(Product, pk=product_id, active=True)
    form = PurchaseForm(request.POST if request.method == "POST" else None)
    quantity = 1
    birth_date = None
    if request.method == "POST" and form.is_valid():
        quantity = form.cleaned_data["quantity"]
        birth_date = form.cleaned_data["birth_date"]
        if "confirm" in request.POST:
            try:
                purchase = Purchase.place(product=product, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                order_ids = request.session.get("order_ids", [])
                request.session["order_ids"] = order_ids + [purchase.pk]
                return redirect("receipt", purchase_id=purchase.pk)
    return render(request, "shop/purchase_form.html", {
        "product": product, "form": form,
        "quote": product.quote(birth_date, quantity),
    })


@require_GET
def receipt(request, purchase_id):
    purchase = get_object_or_404(
        Purchase.objects.select_related("product"), pk=purchase_id,
        pk__in=request.session.get("order_ids", []),
    )
    return render(request, "shop/receipt.html", {"purchase": purchase})


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})
