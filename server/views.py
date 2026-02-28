import ast
from collections import defaultdict
import datetime
from functools import partial
import itertools

from django.core import paginator
import django.db.models
from django.db.models import Q
import django.template
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, reverse

import ob_taxonomy.models as ob_models
import server.models as models


GROUP_NAMES = ('elements', 'nested_objects', 'element_arrays', 'object_arrays')
CURRENTLY_IMPLEMENTED_PRODUCTS = ('prodbattery', 'prodcell', 'prodmodule')


def model_to_ob_json(model, group=False, human_readable_enums=False):
    ob_json_grouped = {k: defaultdict(dict) for k in GROUP_NAMES}
    ob_model = ob_models.OBObject.objects.get(name=model._meta.object_name)
    for element in ob_model.all_elements().order_by('name'):
        if element.item_type.units.exists():
            unit = getattr(model, f'{element.name}_Unit')
            if human_readable_enums and unit != '':
                unit = getattr(models, f'{element.item_type.name}Unit')(unit).label
            ob_json_grouped['elements'][element.name]['Unit'] = unit
        value = getattr(model, f'{element.name}_Value')
        if (
            human_readable_enums and value != ''
            and element.item_type.name != 'UUIDItemType'  # FIXME taxonomy bug: this item type defines enums, but it should not
            and element.item_type.enums.exists()
        ):
            if element.item_type.name == 'ProdTypeItemType' and value == 'ProdCell':
                # FIXME taxonomy bug: ProdCell is missing from the enums of ProdTypeItemType
                value = 'Cell'
            else:
                value = getattr(models, f'{element.item_type.name}Enum')(value).label
        ob_json_grouped['elements'][element.name]['Value'] = value
    for nested_object in ob_model.all_nested_objects().order_by('name'):
        if getattr(model, nested_object.name) is not None:
            ob_json_grouped['nested_objects'][nested_object.name] = model_to_ob_json(getattr(model, nested_object.name), group=group, human_readable_enums=human_readable_enums)
        else:
            ob_json_grouped['nested_objects'][nested_object.name] = None
    for element_array in ob_model.all_element_arrays().order_by('name'):
        ob_json_grouped['element_arrays'][element_array.name] = []
        for v in getattr(model, element_array.name).all():
            item_json = {}
            if element_array.items.item_type.units.exists():
                item_json['Unit'] = getattr(v, 'Unit')
            item_json['Value'] = getattr(v, 'Value')
            ob_json_grouped['element_arrays'][element_array.name].append(item_json)
    for object_array in ob_model.all_object_arrays().order_by('name'):
        if object_array.name == 'SubstituteProducts':
            ob_json_grouped['object_arrays'][object_array.name] = []
        else:
            ob_json_grouped['object_arrays'][object_array.name] = [
                model_to_ob_json(v, group=group, human_readable_enums=human_readable_enums)
                for v in getattr(model, object_array.name).all()
            ]
    ob_json_grouped = {
        group_name: dict(group) for group_name, group in ob_json_grouped.items()
    }
    if group:
        return ob_json_grouped
    return dict(itertools.chain.from_iterable((group.items() for group in ob_json_grouped.values())))


# def get_form_dict(ob_model, d, parent_name=''):
#     name = ob_model.name
#     form_dict = dict(
#         name=name,
#         form=None,
#         object_form_dicts=[],
#         array_form_dicts=[]
#     )
#     form_initial = {}
#     form_prefix = name.lower() if parent_name == '' else f'{parent_name}-{name.lower()}'
#     for element in ob_model.all_elements():
#         match element.taxonomy_element.name:
#             case 'TaxonomyElementString':
#                 default = dict(Value='')
#             case _:
#                 default = dict(Value=None)
#                 if element.item_type.units.exists():
#                     default['Unit'] = ''
#         form_initial[element.name] = d.get(element.name, default)
#     for nested_object in ob_model.all_nested_objects():
#         if d[nested_object.name] is not None:
#             form_dict['object_form_dicts'].append(get_form_dict(nested_object, d[nested_object.name], parent_name=form_prefix))
#     for element_array in ob_model.all_element_arrays():
#             prefix_plural = f'{form_prefix}-{element_array.name.lower()}'
#             form_dict['array_form_dicts'].append(dict(
#                 plural=element_array.name,
#                 prefix_plural=prefix_plural,
#                 object_form_dicts=[
#                     get_form_dict(element_array.items, o, parent_name=f'{prefix_plural}-{i}')
#                     for i, o in enumerate(d[element_array.name])
#                 ]
#             ))
#     for object_array in ob_model.all_object_arrays():
#         prefix_plural = f'{form_prefix}-{object_array.name.lower()}'
#         form_dict['array_form_dicts'].append(dict(
#             plural=object_array.name,
#             prefix_plural=prefix_plural,
#             object_form_dicts=[
#                 get_form_dict(object_array.items, o, parent_name=f'{prefix_plural}-{i}')
#                 for i, o in enumerate(d[object_array.name])
#             ]
#         ))
#     form_dict['form'] = getattr(forms, name)(initial=form_initial, prefix=form_prefix)
#     return form_dict


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


def _obobjectsubset(group_name, obobject, key_csv):
    group = {k: obobject[group_name][k] for k in key_csv.split(',')}
    return {group_name: group}


for group_name in GROUP_NAMES:
    django.template.defaulttags.register.filter(f'obobject_{group_name}_subset', partial(_obobjectsubset, group_name))


def get_search_context(request):
    current_search_query = request.GET.get('q', '')
    current_source_country = request.GET.get('SourceCountry', '')
    US = models.ISOCountryItemTypeEnum.US
    source_country_options = [
        ('', 'Any source country', '' == current_source_country),
        (US.value, US.label, US.value == current_source_country),
        *(
            (e.value, e.label, e.value == current_source_country)
            for e in sorted(models.ISOCountryItemTypeEnum, key=lambda e: e.label)
            if e is not US
        )
    ]
    return dict(search_query=current_search_query, source_country_options=source_country_options)


def product_detail_by_ProdID(request, ProdID_Value):
    # subclass_reverse_names = map(str.lower, ob_models.OBObject.filter(comprises__name='Product').values_list('name', flat=True))
    subclass_reverse_names = CURRENTLY_IMPLEMENTED_PRODUCTS
    product = get_object_or_404(
        models.Product.objects.select_related(*subclass_reverse_names),
        ProdID_Value=ProdID_Value,
    )
    product = determine_product_subclass(product, subclass_reverse_names=subclass_reverse_names)
    product_serialized = model_to_ob_json(product, group=True, human_readable_enums=True)
    return render(
        request,
        'server/product_detail.html',
        context=dict(
            search_context=get_search_context(request),
            product=product_serialized,
        )
    )


def product_detail_by_ProdCode(request, ProdCode_Value):
    product = get_object_or_404(models.Product, ProdCode_Value=ProdCode_Value)
    return product_detail_by_ProdID(request, ProdID_Value=product.ProdID_Value)


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


def product_list(request):
    search_query = request.GET.get('q', '')
    search_source_country = request.GET.get('SourceCountry', '')
    products = models.Product.objects.all()
    if search_source_country != '':
        products = products.filter(
            SourceCountries__CountryOfManufacture_Value__icontains=search_source_country,
        )
    products = (
        products.values(
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
        .order_by(
            'ProdType_Value',
            'ProdCode_Value',
        )
    )
    search_query = f'?q={search_query}&'
    return render(
        request,
        'server/product_list.html',
        context=dict(
            search_context=get_search_context(request),
            search_query=search_query,
            page_products=paginator.Paginator(products, 20).get_page(request.GET.get('page'))
        )
    )

def product_list_us_domestic(request):
    search_query = request.GET.get('q', '')
    products = models.Product.objects.filter(
        SourceCountries__CountryOfManufacture_Value__icontains=models.ISOCountryItemTypeEnum.US,
    )
    products = (
        products.values(
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
        .order_by(
            'ProdType_Value',
            'ProdCode_Value',
        )
    )
    search_query = f'?q={search_query}&'
    return render(
        request,
        'server/product_list_us_domestic.html',
        context=dict(
            search_context=get_search_context(request),
            search_query=search_query,
            page_products=paginator.Paginator(products, 20).get_page(request.GET.get('page'))
        )
    )
