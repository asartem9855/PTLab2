from django.urls import path

from . import controllers

urlpatterns = [
    path("", controllers.index, name="index"),
    path("buy/<int:product_id>/", controllers.buy, name="buy"),
    path("orders/<int:purchase_id>/", controllers.receipt, name="receipt"),
    path("health/", controllers.health, name="health"),
]
