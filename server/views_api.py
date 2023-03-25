from collections import OrderedDict

from django import db, conf, shortcuts
from django.templatetags import static
from rest_framework import response, decorators

from server import models, ob_item_types as obit, serializers, pagination


def build_query(prod_types, request):
    subqueries = []
    for pt in prod_types:
        info_dict = OrderedDict()
        build_subquery_info(request.data, info_dict, pt, None)
        subqueries.append(_build_subquery(info_dict))
    subquery_strings = []
    params = dict()
    has_group_by = False
    for subquery, subquery_params, subquery_has_group_by in subqueries:
        subquery_strings.append(subquery)
        params.update(subquery_params)
        has_group_by = has_group_by or subquery_has_group_by
    query = ' UNION '.join(subquery_strings)

    if 'WINDOW' in query:  # has group by
        default_page_limit = conf.settings.REST_FRAMEWORK['PAGE_SIZE']
        max_page_limit = conf.settings.REST_FRAMEWORK['MAX_LIMIT']
        current_offset = int(request.GET.get('offset_SubstituteProducts', 0))
        params['offset_SubstituteProducts'] = current_offset + 2  # row_number starts counting at 1, and the first row is the first product. Therefore, the first SubstituteProduct is at row_number 2
        params['limit_SubstituteProducts'] = current_offset + min(max_page_limit, int(request.GET.get('limit_SubstituteProducts', default_page_limit))) + 2
        print('offset', params['offset_SubstituteProducts'], 'limit', params['limit_SubstituteProducts'])

    return query, params, has_group_by


def _SELECT(relation, join_col, has_group_by: bool, window_name='query_group'):
    columns = [f'{relation}.{join_col}']
    if has_group_by:
        columns += [
            f'min({relation}.{join_col}) OVER {window_name} as first',
            f'ROW_NUMBER() OVER {window_name} as group_row'
        ]
    return f"SELECT {', '.join(columns)} "


def _FROM_TABLES(info_dict):
    FROM = 'FROM '
    relation_first, join_col_first = None, None
    for i, (name, m_info_list) in enumerate(info_dict.items()):
        m_db = f'server_{name.lower()}'
        for m_info in m_info_list:
            parent_join_column = m_info['parent_join_column']
            join_col = m_info['join_col']
            parent_relation = m_info['parent_relation']
            relation = m_info['relation']
            if i == 0:
                table = f'{m_db} as {relation}'
                relation_first, join_col_first = relation, join_col
            else:
                table = f'JOIN {m_db} as {relation}'
            if parent_relation is not None:
                table = f'{table} ON {parent_relation}.{parent_join_column}={relation}.{join_col}'
            FROM += f'{table} '
    return FROM, relation_first, join_col_first


def _get_WHERE_GROUP_BY_clauses(info_dict):
    params = {}
    wheres, group_bys = [], []
    for i, (name, m_info_list) in enumerate(info_dict.items()):
        for m_info in m_info_list:
            relation = m_info['relation']
            fields = m_info['fields']
            for f, v in fields:
                if v == '':
                    group_bys.append(f'{relation}.{f}')
                else:
                    param_name = f'{name}_{f}'
                    params[param_name] = v
                    wheres.append(f'{relation}.{f} REGEXP %({param_name})s')
    return wheres, group_bys, params


def _WHERE(where_clauses):
    return f"WHERE {' AND '.join(where_clauses)} "


def _WINDOW_PARTITION_BY(relation, join_col, group_by_clauses, window_name='query_group'):
    return f"WINDOW {window_name} as (PARTITION BY {', '.join(group_by_clauses)} ORDER BY {relation}.{join_col})"


def _PaginationSubstitueProducts(query_relation, row_num_col='group_row',
                                 offset_param='offset_SubstituteProducts',
                                 limit_param='limit_SubstituteProducts'):
    return f'WHERE ({query_relation}.{row_num_col}=1 OR {query_relation}.{row_num_col}>=%({offset_param})s AND {query_relation}.{row_num_col}<%({limit_param})s) '


def _build_subquery(info_dict):
    wheres, group_bys, params = _get_WHERE_GROUP_BY_clauses(info_dict)
    has_wheres, has_group_by = len(wheres) > 0, len(group_bys) > 0
    FROM_TABLES, relation_first, join_col_first = _FROM_TABLES(info_dict)
    SELECT = _SELECT(relation_first, join_col_first, has_group_by)
    WHERE = ''
    if has_wheres:
        WHERE = _WHERE(wheres)
    subquery = f'{SELECT}{FROM_TABLES}{WHERE}'
    WINDOW_PARTITION_BY = ''
    PaginationSubstitueProducts = ''
    if has_group_by:
        WINDOW_PARTITION_BY = _WINDOW_PARTITION_BY(relation_first, join_col_first, group_bys)
        query_groups_relation = 'query_group'
        PaginationSubstitueProducts = _PaginationSubstitueProducts(query_groups_relation)
        subquery = f'SELECT id, first FROM ({subquery}{WINDOW_PARTITION_BY}) as {query_groups_relation} {PaginationSubstitueProducts}'
    print(subquery)
    return subquery, params, has_group_by


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
        product_id_groups = _product_list_query(request)
    else:
        product_ids = models.Product.objects.values_list('id', flat=True)
        product_id_groups = [(i, []) for i in product_ids]
    paginator = pagination.ProductsPagination()  # works on lists too
    results_page = paginator.paginate_queryset(product_id_groups, request)
    results = OrderedDict()
    results.update(serializers.serialize_product_id_groups(results_page))
    return paginator.get_paginated_response(results.values())


def _product_list_query(request):
    prod_types = obit.get_schema_subclasses('Product')
    query, params, has_group_by = build_query(prod_types, request)
    product_groups = OrderedDict()
    with db.connection.cursor() as cursor:
        cursor.execute(query, params=params)
        # min(id) on empty table returns null
        for row in cursor.fetchall():
            if has_group_by:
                product_id, first_id = row
                if first_id not in product_groups:
                    product_groups[first_id] = []
                if product_id != first_id:
                    product_groups[first_id].append(product_id)
            else:
                product_id, = row  # unpack length one tuple
                product_groups[product_id] = []
        return list(product_groups.items())


@decorators.api_view(['GET'])
def product_detail(request, **kwargs):
    for p in obit.get_schema_subclasses('Product'):
        if len(res := list(serializers.serialize_by_ids(p, [get_product_id(kwargs)]).values())) > 0:
            return response.Response(res[0])
    return response.Response()


def product_api_schema(request):
    return shortcuts.render(
        request,
        'server/schema_viewer.html',
        context=dict(
            title='Product Registry - Product API Schema',
            schema_url=static.static('server/schemas/api/product.yaml')
        )
    )


def obtaxonomy_api_schema(request):
    return shortcuts.render(
        request,
        'server/schema_viewer.html',
        context=dict(
            title='Product Registry - OB Taxonomy',
            schema_url=static.static('server/schemas/Master-OB-OpenAPI.json')
        )
    )
