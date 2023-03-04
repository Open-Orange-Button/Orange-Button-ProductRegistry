from collections import OrderedDict
import itertools

from django import db
from rest_framework import response, decorators

from server import models, ob_item_types as obit, serializers, pagination


def build_query(prod_types, data):
    subqueries = []
    for pt in prod_types:
        info_dict = OrderedDict()
        build_subquery_info(data, info_dict, pt, None)
        subqueries.append(build_subquery(info_dict))
    subquery_strings = []
    params = dict()
    for subquery, subquery_params in subqueries:
        subquery_strings.append(subquery)
        params.update(subquery_params)
    query = ' UNION '.join(subquery_strings)
    return query, params


def build_subquery(info_dict):
    subquery = 'SELECT id, first FROM ('
    params = {}
    filters = []
    group_bys = []
    relation_first = ''
    join_col_first = ''
    for i, (name, m_info_list) in enumerate(info_dict.items()):
        m_db = f'server_{name.lower()}'
        for m_info in m_info_list:
            parent_join_column = m_info['parent_join_column']
            join_col = m_info['join_col']
            parent_relation = m_info['parent_relation']
            relation = m_info['relation']
            fields = m_info['fields']
            if parent_relation is None:
                if i == 0:
                    subquery += f'SELECT {relation}.{join_col}, min({relation}.{join_col}) OVER product_group as first, ROW_NUMBER() OVER product_group as group_row FROM {m_db} as {relation} '
                    relation_first = relation
                    join_col_first = join_col
                else:
                    subquery += f'JOIN {m_db} as {relation} '
            else:
                subquery += f'JOIN {m_db} as {relation} ON {parent_relation}.{parent_join_column}={relation}.{join_col} '
            for f, v in fields:
                if v == '':
                    group_bys.append(f'{relation}.{f}')
                else:
                    param_name = f'{name}_{f}'
                    params[param_name] = v
                    filters.append(f'{relation}.{f} REGEXP %({param_name})s')
    subquery += f'WINDOW product_group as (PARTITION BY {", ".join(group_bys)} ORDER BY {relation_first}.{join_col_first})) as product_groups '
    clause_info = (('WHERE', ' AND ', filters),)
    clauses = tuple(f'{kw} {joiner.join(args)}' for kw, joiner, args in clause_info
               if len(args) > 0)
    subquery += ' '.join(clauses)
    subquery += f'{"AND" if len(clauses) > 0 else "WHERE"} (product_groups.group_row=1 OR product_groups.group_row>=5 AND product_groups.group_row<10)'
    print(subquery)
    return subquery, params


def build_subquery_info(query_data, info_dict, name, parent_name):
    superclass = obit.get_schema_superclass(name)
    if superclass is not None:
        # ensure the superclass table can be joined on
        build_subquery_info(query_data, info_dict, superclass, None)

    # bucket the fields declared on the OB definition, excluding superclass fields
    elements, objects, arrays = [], [], []
    for f in set(obit.all_fields_of_ob_object(name, include_inherited=False)).intersection(set(query_data.keys())):
        match obit.get_schema_type(f):
            case obit.OBType.Element:
                elements.append(f)
            case obit.OBType.Object:
                objects.append(f)
            case obit.OBType.Array:
                arrays.append(f)

    # create the query info about this model of the query_data
    if name not in info_dict:
        info_dict[name] = []
    parent_model_name = superclass or parent_name or None
    parent_relation = None
    parent_join_column = None
    parent_model = None
    if parent_model_name is not None:
        # this model table needs to join on the parent table
        parent_rel_number = len(info_dict.get(parent_model_name)) - 1
        parent_relation = f'{parent_model_name}{parent_rel_number}'
        parent_model = getattr(models, parent_model_name)
        parent_join_column = parent_model._meta.pk.column
    rel_number = len(info_dict.get(name))
    relation = f'{name}{rel_number}'
    m_info = dict(
        fields=[], parent_join_column=parent_join_column,
        join_col=getattr(models, name)._meta.pk.column,
        parent_relation=parent_relation, relation=relation
    )

    # record the fields in the query_data
    for f in elements:
        for p in obit.Primitive:
            if (v := query_data[f].get(p.name, None)) is not None:
                m_info['fields'].append((f'{f}_{p.name}', v))

    info_dict[name].append(m_info)  # leave out if fields length is zero?

    # add query info about this model's nested objects and arrays
    for o in objects:
        build_subquery_info(query_data[o], info_dict, o, name)
    for a in arrays:
        a_singular = obit.array_to_singular(a)
        for am in query_data[a]:
            build_subquery_info(am, info_dict, a_singular, name)


def get_product_id(kwargs):
    match kwargs:
        case {'uuid': ProdID_Value}:
            query = dict(ProdID_Value=ProdID_Value)
        case {'ProdCode_Value': ProdCode_Value}:
            query = dict(ProdCode_Value=ProdCode_Value)
        case _:
            query = dict(id=None)
    return models.Product.objects.filter(**query).values_list('id', flat=True)[0]


@decorators.api_view(['GET', 'POST'])
def product_list(request):
    if request.method == 'POST':
        product_id_groups = _product_list_group_by(request.data)
    else:
        product_ids = models.Product.objects.values_list('id', flat=True)
        product_id_groups = [(i, []) for i in product_ids]
    paginator = pagination.ProductsPagination()  # works on lists too
    results_page = paginator.paginate_queryset(product_id_groups, request)
    results = OrderedDict()
    results.update(serializers.serialize_product_id_groups(results_page))
    return paginator.get_paginated_response(results.values())


def _product_list_group_by(post_data):
    prod_types = obit.get_schema_subclasses('Product')
    query, params = build_query(prod_types, post_data)
    product_groups = OrderedDict()
    with db.connection.cursor() as cursor:
        cursor.execute(query, params=params)
        # min(id) on empty table returns null
        for product_id, first_id in cursor.fetchall():
            if first_id not in product_groups:
                product_groups[first_id] = []
            if product_id != first_id:
                product_groups[first_id].append(product_id)
        return list(product_groups.items())


@decorators.api_view(['GET'])
def product_detail(request, **kwargs):
    for p in obit.get_schema_subclasses('Product'):
        if len(res := list(serializers.serialize_by_ids(p, [get_product_id(kwargs)]).values())) > 0:
            return response.Response(res[0])
    return response.Response()
