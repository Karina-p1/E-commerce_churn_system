from django.apps import AppConfig
# This file defines the configuration for the 'orders' app in the e-commerce project. It specifies the default auto field type and the name of the app. This configuration is used by Django to set up the app correctly when it is included in the project.
class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.orders'