from django import shortcuts
from django.db.models import Q
from django.core import paginator

from server import models, ob_item_types as obit, serializers, forms


def get_product_id(kwargs):
    match kwargs:
        case {'uuid': ProdID_Value}:
            query = dict(ProdID_Value=ProdID_Value)
        case {'ProdCode_Value': ProdCode_Value}:
            query = dict(ProdCode_Value=ProdCode_Value)
        case _:
            query = dict(id=None)
    return models.Product.objects.filter(**query).values_list('id', flat=True)[0]


def get_form_dict(name, d, parent_name=''):
    form_dict = dict(
        name=name,
        form=None,
        object_form_dicts=[],
        array_form_dicts=[]
    )
    form_initial = {}
    form_prefix = name.lower() if parent_name == '' else f'{parent_name}-{name.lower()}'
    for k, v in d.items():
        match obit.get_schema_type(k):
            case obit.OBType.Element:
                form_initial[k] = v
            case obit.OBType.Object:
                form_dict['object_form_dicts'].append(get_form_dict(k, v, parent_name=form_prefix))
            case obit.OBType.Array:
                prefix_plural = f'{form_prefix}-{k.lower()}'
                form_dict['array_form_dicts'].append(dict(
                    plural=k,
                    prefix_plural=prefix_plural,
                    object_form_dicts=[get_form_dict(obit.array_to_singular(k), o, parent_name=f'{prefix_plural}-{i}') for i, o in enumerate(v)]
                ))
    form_dict['form'] = getattr(forms, name)(initial=form_initial, prefix=form_prefix)
    return form_dict


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
        .order_by('id')
    )
    search_query = f'?q={search_query}&'
    return shortcuts.render(
        request,
        'server/product_list.html',
        context=dict(
            search_query=search_query,
            page_products=paginator.Paginator(products, 20).get_page(request.GET.get('page'))
        )
    )


def product_detail(request, **kwargs):
    if request.method == 'POST':
        pass
    else:
        for p in obit.get_schema_subclasses('Product'):
            if len(res := list(serializers.serialize_by_ids(p, ids=[get_product_id(kwargs)]).values())) > 0:
                product = res[0]
                form_dict = get_form_dict(p, product)
                return shortcuts.render(
                    request,
                    'server/forms/product.html',
                    context=dict(
                        product=product,
                        form_dict=form_dict
                    )
                )
