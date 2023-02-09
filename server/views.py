from collections import OrderedDict

from django import shortcuts
from django.views import generic
from rest_framework import viewsets, response
from rest_framework import decorators

from server import models, ob_item_types as obit, serializers, forms


class ListProdModule(generic.ListView):
    model = models.ProdModule
    queryset = models.ProdModule.objects.all()[800:800+20]


class DetailProdModule(generic.DetailView):
    model = models.ProdModule
    queryset = models.ProdModule.objects.all()

    def get_object(self):
        match self.kwargs:
            case {'uuid': ProdID_Value}:
                query = dict(ProdID_Value=ProdID_Value)
            case {'ProdCode_Value': ProdCode_Value}:
                query = dict(ProdCode_Value=ProdCode_Value)
            case _:
                query = dict(id=None)
        return shortcuts.get_object_or_404(self.model, **query)


def get_prodmodule(kwargs):
    match kwargs:
        case {'uuid': ProdID_Value}:
            query = dict(ProdID_Value=ProdID_Value)
        case {'ProdCode_Value': ProdCode_Value}:
            query = dict(ProdCode_Value=ProdCode_Value)
        case _:
            query = dict(id=None)
    return shortcuts.get_object_or_404(models.ProdModule, **query)


def updateviewprodmodule(request, **kwargs):
    if request.method == 'POST':
        pass
    else:
        prodmodule = get_prodmodule(kwargs)
        prodmodule_form = forms.ProdModule(initial=prodmodule, prefix='prodmodule')
        dimension_form = forms.Dimension(initial=prodmodule.Dimension, prefix='dimension')
    return shortcuts.render(
        request,
        'server/prodmodule_form.html',
        context=dict(
            prodmodule=prodmodule,
            prodmodule_form=prodmodule_form,
            dimension_form=dimension_form
        )
    )


def get_prod_type_by_fields(fields):
    return [m for m in models.PROD_MODLES
            if len(fields - set(obit.all_fields_of_ob_object(m))) == 0]


def build_query(prod_types, data):
    subqueries = []
    for pt in prod_types:
        info_dict = OrderedDict()
        build_subquery_info(data, info_dict, pt, None)
        subqueries.append((pt, build_subquery(info_dict)))
    query = ' UNION '.join(f'{sq}' for pt, sq in subqueries)
    return query


def build_subquery(info_dict):
    subquery = ''
    filters = []
    group_bys = []
    for m, m_info_list in info_dict.items():
        m_db = f'server_{m}'
        for m_info in m_info_list:
            parent_join_col = m_info['parent_join_col']
            join_col = m_info['join_col']
            parent_relation = m_info['parent_relation']
            relation = m_info['relation']
            fields = m_info['fields']
            if parent_relation is None:
                if subquery == '':
                    subquery = f'SELECT min({relation}.{join_col}) as {join_col} from {m_db} as {relation} '
                else:
                    subquery += f'JOIN {m_db} as {relation} '
            else:
                subquery += f'JOIN {m_db} as {relation} ON {parent_relation}.{parent_join_col}={relation}.{join_col} '
            for f, v in fields:
                if v == '':
                    group_bys.append(f'{relation}.{f}')
                else:
                    filters.append(f'{relation}.{f} REGEXP "{v}"')
    clause_info = (('WHERE', ' AND ', filters), ('GROUP BY', ', ', group_bys))
    clauses = (f'{kw} {joiner.join(args)}' for kw, joiner, args in clause_info
               if len(args) > 0)
    subquery += " ".join(clauses)
    return subquery


def build_subquery_info(data, info_dict, m, mp):
    sc = obit.get_schema_superclass(m)
    if sc is not None:
        build_subquery_info(data, info_dict, sc, None)
    direct_fields = set(obit.all_fields_of_ob_object(m, include_inherited=False))
    data_fields = set(data.keys())
    elements = []
    objects = []
    arrays = []
    for f in direct_fields.intersection(data_fields):
        match obit.get_schema_type(f):
            case obit.OBType.Element:
                elements.append(f)
            case obit.OBType.Object:
                objects.append(f)
            case obit.OBType.Array:
                arrays.append(f)
    if m not in info_dict:
        info_dict[m] = []
    parent_model_name = sc or mp or None
    parent_relation = None
    parent_join_col = None
    parent_model = None
    if parent_model_name is not None:
        parent_rel_number = len(info_dict.get(parent_model_name)) - 1
        parent_relation = f'{parent_model_name}{parent_rel_number}'
        parent_model = getattr(models, parent_model_name)
        parent_join_col = parent_model._meta.pk.column
    rel_number = len(info_dict.get(m))
    relation = f'{m}{rel_number}'
    model = getattr(models, m)
    m_info = dict(fields=[], parent_join_col=parent_join_col,
                  join_col=model._meta.pk.column,
                  parent_relation=parent_relation,
                  relation=relation)
    for f in elements:
        for p in obit.Primitive:
            if (v := data[f].get(p.name, None)) is not None:
                m_info['fields'].append((f'{f}_{p.name}', v))
    info_dict[m].append(m_info)  # leave out if fields length is zero?
    for o in objects:
        build_subquery_info(data[o], info_dict, o, m)
    for a in arrays:
        a_singular = obit.array_to_singular(a)
        for am in data[a]:
            build_subquery_info(am, info_dict, a_singular, m)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.Product.objects.all()

    def get_view_name(self):
        if self.detail:
            if hasattr(self, 'kwargs'):
                lookup_field_value = self.kwargs.get(self.lookup_field, '')
                return f'Product {lookup_field_value}'
            return 'Product'
        return 'Products'

    def retrieve(self, request, *args, **kwargs):
        product = shortcuts.get_object_or_404(models.Product, **{self.lookup_field: kwargs[self.lookup_field]})
        for p in obit.get_schema_subclasses('Product'):
            if len(res := list(serializers.serialize_by_ids(p, [product.id]).values())) != 0:
                return response.Response(res[0])

    def list(self, request, *args, **kwargs):
        products = models.Product.objects.values_list('id', flat=True)
        results_page = self.paginator.paginate_queryset(products, request)
        results = OrderedDict()
        for p in obit.get_schema_subclasses('Product'):
            results.update(serializers.serialize_by_ids(p, results_page))
        return self.get_paginated_response(results.values())

    def get_serializer_context(self):
        super_context = super().get_serializer_context()
        query_params = self.request.query_params
        context = dict(unconfirmed_edits=query_params.get('unconfirmed_edits', '') == 'true')
        context.update(super_context)
        return context

    @decorators.action(detail=False, methods=['post'])
    def group(self, request, *args, **kwargs):
        data = request.data
        prod_types = get_prod_type_by_fields(set(data.keys()))
        query = build_query(prod_types, data)
        products = models.Product.objects.raw(query)
        results_page = self.paginator.paginate_queryset(products, request)
        results = self.get_serializer(results_page, many=True).data
        return self.get_paginated_response(results)


class ProductByProdCodeViewSet(ProductViewSet):
    lookup_field = 'ProdCode_Value'


class ProductByProdIDVeiwSet(ProductViewSet):
    lookup_field = 'ProdID_Value'
    lookup_value_regex = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
