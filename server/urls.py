from django.urls import path

from . import views


# app_name = 'product'
app_name = 'webpage'
urlpatterns = [
    # path('', views.product_list, name='list'),
    # path('<uuid:ProdID_Value>', views.product_detail_by_ProdID, name='detail'),
    path('', views.product_list, name='product-list'),
    path('<uuid:ProdID_Value>/', views.product_detail_by_ProdID, name='product-detail-prodid'),
    path('<uuid:ProdID_Value>/json', views.product_json, name='product-json'),
    # path('product/<slug:ProdCode_Value>/', views.product_detail, name='product-detail-prodcode'),
]
