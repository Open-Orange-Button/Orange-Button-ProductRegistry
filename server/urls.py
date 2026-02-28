from django.urls import path

from . import views


app_name = 'product'
urlpatterns = [
    path('', views.product_list, name='list'),
    path('us-domestic-content/', views.product_list_us_domestic, name='list-us-domestic'),
    path('<uuid:ProdID_Value>/', views.product_detail_by_ProdID, name='detail-prodid'),
    path('<uuid:ProdID_Value>/json/', views.product_json, name='json'),
    path('<slug:ProdCode_Value>/', views.product_detail_by_ProdCode, name='detail-prodcode'),
]
