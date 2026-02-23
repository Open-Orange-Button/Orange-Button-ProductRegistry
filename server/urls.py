from django.urls import path

from . import views


app_name = 'product'
urlpatterns = [
    path('', views.product_list, name='list'),
    path('<uuid:ProdID_Value>/', views.product_detail_by_ProdID, name='detail-prodid'),
    path('<uuid:ProdID_Value>/json', views.product_json, name='json'),
    path('<slug:ProdCode_Value>/', views.product_detail_by_ProdCode, name='detail-prodcode'),
]
