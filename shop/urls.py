from django.contrib.auth import views as auth_views
from django.urls import path

from . import controllers

urlpatterns = [
    path("", controllers.index, name="index"),
    path("register/", controllers.register, name="register"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("buy/<int:product_id>/", controllers.buy, name="buy"),
    path("orders/", controllers.orders, name="orders"),
    path("orders/<int:purchase_id>/", controllers.receipt, name="receipt"),
    path("health/", controllers.health, name="health"),
]
