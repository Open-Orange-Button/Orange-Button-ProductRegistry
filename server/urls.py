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
from django import urls

from server import views


urlpatterns = [
    urls.path('prodmodule/', views.ListProdModule.as_view(), name='prodmodule'),
    # urls.path('prodmodule/<uuid:uuid>/', views.DetailProdModule.as_view(), name='prodmodule-detail-prodid'),
    urls.path('prodmodule/<uuid:uuid>/', views.UpdateViewProdModule.as_view(), name='prodmodule-update-prodid'),
    urls.path('prodmodule/<slug:ProdCode_Value>/', views.DetailProdModule.as_view(), name='prodmodule-detail-prodcode'),
    urls.path('api/v1/', urls.include('server.urls_api'))
]
