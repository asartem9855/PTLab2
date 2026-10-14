from django.contrib import admin

from .models import Customer, Product, Purchase

admin.site.site_header = "Линия · управление магазином"
admin.site.site_title = "Линия"
admin.site.index_title = "Товары, покупатели и заказы"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "active")
    list_filter = ("category", "active")
    search_fields = ("name",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "birth_date")
    search_fields = ("user__username", "user__first_name")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "product", "quantity",
                    "discount_percent", "total_price", "date")
    list_filter = ("discount_percent", "date")
    search_fields = ("person", "product__name")
    readonly_fields = (
        "product", "customer", "person", "address", "date", "quantity",
        "birth_date", "unit_price", "discount_percent", "total_price",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
