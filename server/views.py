import ast
from collections import defaultdict
import datetime
import itertools

from django.core import paginator
import django.db.models
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, reverse

import ob_taxonomy.models as ob_models
import server.models as models
import server.forms as forms


CURRENTLY_IMPLEMENTED_PRODUCTS = ('prodbattery', 'prodmodule')


def model_to_ob_json(model):
    ob_json = defaultdict(dict)
    ob_model = ob_models.OBObject.objects.get(name=model._meta.object_name)
    for element in ob_model.all_elements():
        if element.item_type.units.exists():
            ob_json[element.name]['Unit'] = getattr(model, f'{element.name}_Unit')
        ob_json[element.name]['Value'] = getattr(model, f'{element.name}_Value')
    for nested_object in ob_model.all_nested_objects():
        if getattr(model, nested_object.name) is not None:
            ob_json[nested_object.name] = model_to_ob_json(getattr(model, nested_object.name))
        else:
            ob_json[nested_object.name] = None
    for element_array in ob_model.all_element_arrays():
        ob_json[element_array.name] = []
        for v in getattr(model, element_array.name).all():
            item_json = {}
            if element_array.items.item_type.units.exists():
                item_json['Unit'] = getattr(v, 'Unit')
            item_json['Value'] = getattr(v, 'Value')
            ob_json[element_array.name].append(item_json)
    for object_array in ob_model.all_object_arrays():
        if object_array.name == 'SubstituteProducts':
            ob_json[object_array.name] = []
        else:
            ob_json[object_array.name] = [
                model_to_ob_json(v)
                for v in getattr(model, object_array.name).all()
            ]
    return ob_json


def get_form_dict(ob_model, d, parent_name=''):
    name = ob_model.name
    form_dict = dict(
        name=name,
        form=None,
        object_form_dicts=[],
        array_form_dicts=[]
    )
    form_initial = {}
    form_prefix = name.lower() if parent_name == '' else f'{parent_name}-{name.lower()}'
    for element in ob_model.all_elements():
        match element.taxonomy_element.name:
            case 'TaxonomyElementString':
                default = dict(Value='')
            case _:
                default = dict(Value=None)
                if element.item_type.units.exists():
                    default['Unit'] = ''
        form_initial[element.name] = d.get(element.name, default)
    for nested_object in ob_model.all_nested_objects():
        if d[nested_object.name] is not None:
            form_dict['object_form_dicts'].append(get_form_dict(nested_object, d[nested_object.name], parent_name=form_prefix))
    for element_array in ob_model.all_element_arrays():
            prefix_plural = f'{form_prefix}-{element_array.name.lower()}'
            form_dict['array_form_dicts'].append(dict(
                plural=element_array.name,
                prefix_plural=prefix_plural,
                object_form_dicts=[
                    get_form_dict(element_array.items, o, parent_name=f'{prefix_plural}-{i}')
                    for i, o in enumerate(d[element_array.name])
                ]
            ))
    for object_array in ob_model.all_object_arrays():
        prefix_plural = f'{form_prefix}-{object_array.name.lower()}'
        form_dict['array_form_dicts'].append(dict(
            plural=object_array.name,
            prefix_plural=prefix_plural,
            object_form_dicts=[
                get_form_dict(object_array.items, o, parent_name=f'{prefix_plural}-{i}')
                for i, o in enumerate(d[object_array.name])
            ]
        ))
    form_dict['form'] = getattr(forms, name)(initial=form_initial, prefix=form_prefix)
    return form_dict


def determine_product_subclass(product, subclass_reverse_names=None):
    if subclass_reverse_names is None:
        # subclass_reverse_names = map(str.lower, ob_models.OBObject.filter(comprises__name='Product').values_list('name', flat=True))
        subclass_reverse_names = CURRENTLY_IMPLEMENTED_PRODUCTS
    for subclass_name in subclass_reverse_names:
        try:
            product = getattr(product, subclass_name)
            return product
        except AttributeError, models.models.ObjectDoesNotExist:
            pass


def product_detail_by_ProdID(request, ProdID_Value):
    # subclass_reverse_names = map(str.lower, ob_models.OBObject.filter(comprises__name='Product').values_list('name', flat=True))
    subclass_reverse_names = CURRENTLY_IMPLEMENTED_PRODUCTS
    product = get_object_or_404(
        models.Product.objects.select_related(*subclass_reverse_names),
        ProdID_Value=ProdID_Value,
    )
    product = determine_product_subclass(product, subclass_reverse_names=subclass_reverse_names)
    name = type(product).__name__
    product_serialized = model_to_ob_json(product)
    print(product_serialized)
    ob_model = ob_models.OBObject.objects.get(name=name)
    form_dict = get_form_dict(ob_model, product_serialized)
    return render(
        request,
        'server/forms/product.html',
        context=dict(
            product=product_serialized,
            form_dict=form_dict
        )
    )


def product_detail_by_ProdCode(request, ProdCode_Value):
    product = get_object_or_404(models.Product, ProdCode_Value=ProdCode_Value)
    return product_detail_by_ProdID(request, product=product)


def product_json(request, ProdID_Value):
    subclass_reverse_names = CURRENTLY_IMPLEMENTED_PRODUCTS
    product = get_object_or_404(
        models.Product.objects.select_related(*subclass_reverse_names),
        ProdID_Value=ProdID_Value,
    )
    product = determine_product_subclass(product, subclass_reverse_names=subclass_reverse_names)
    ob_json = model_to_ob_json(product)
    response = JsonResponse(ob_json, json_dumps_params=dict(indent=4))
    response['Content-Disposition'] = f'attachment; filename="{ProdID_Value}.json"'
    return response


def product_list(request, **kwargs):
    search_query = request.GET.get('q', '')
    products = (
        models.Product.objects.values(
            'ProdType_Value',
            'ProdMfr_Value',
            'ProdName_Value',
            'ProdCode_Value',
            'ProdID_Value'
        )
        .filter(
            Q(Description_Value__icontains=search_query)
            | Q(ProdCode_Value__icontains=search_query)
            | Q(ProdMfr_Value__icontains=search_query)
            | Q(ProdName_Value__icontains=search_query)
            | Q(ProdType_Value__icontains=search_query)
        )
        .order_by('ProdCode_Value')
    )
    search_query = f'?q={search_query}&'
    return render(
        request,
        'server/product_list.html',
        context=dict(
            search_query=search_query,
            page_products=paginator.Paginator(products, 20).get_page(request.GET.get('page'))
        )
    )
