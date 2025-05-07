"""product_registry URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django import urls, views as django_views

from server import views


urlpatterns = [
    urls.path('product/', views.product_list, name='product-list'),
    urls.path('product/<uuid:uuid>/', views.product_detail, name='product-detail-prodid'),
    urls.path('product/<slug:ProdCode_Value>/', views.product_detail, name='product-detail-prodcode'),
    urls.path('', django_views.generic.base.RedirectView.as_view(url=urls.reverse_lazy('webpage:product-list')), name='root')
]
