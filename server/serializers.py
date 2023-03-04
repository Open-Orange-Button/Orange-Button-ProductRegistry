from collections import OrderedDict
import itertools

import flatten_json

from server import models
from server import ob_item_types as obit


def wrap_with_id_and_unflatten(dict_list):
    """
    Parameters
    ----------
    dict_list: list(dict)
        A list of dictionaries that contain the key ``id``.

    Returns
    -------
        OrderedDict mapping the id of each dict in ``dict_list`` to the dict itself.
        The OrderedDict has the form
        .. code-block::

           {
                "<id_value>": {
                    "id": "<id_value>",
                    "<key1>": "<value1>",
                    "<key2>": "<value2>",
                    ...
                }
           }
    """
    return OrderedDict([(o['id'], flatten_json.unflatten(o, '_')) for o in dict_list])


def get_values_by_ids(name, ids, fields_include=None):
    """
    Gets an OrderedDict of row ids to row data dicts of a Django model given a list of row ids.

    Parameters
    ----------
    name: str
        The name of a Django model defined in ``server.models``.

    ids: Iterable(int)
        An iterable of row ids of the Django model's database table.

    fields_include: Dict(str, Any)
        An dict whose keys are columns of the Django model's database table.

    Returns
    -------
        OrderedDict mapping row id to row data dict.
    """
    query = getattr(models, name).objects.filter(id__in=ids)
    if fields_include is None:
        query = query.values()
    else:
        query = query.values(*fields_include.keys())
    return wrap_with_id_and_unflatten(query)


def get_values_by_fk_ids(name, fk_name, fk_ids, fields_include=None):
    """
    Gets an OrderedDict of row ids to row data dicts of a Django model given a
    list of ids of table that the Django model has a one-to-many relationship
    with. ``fk_name:1->M:name``.

    Parameters
    ----------
    name: str
        The name of a Django model defined in ``server.models``.

    fk_name: str
        The name of a Django model defined in ``server.models`` that ``name``
        has a one-to-many relationship with.

    fk_ids: Iterable(int)
        An iterable of row ids of the ``fk_name`` database table.

    fields_include: dict(str, Any)
        An dict whose keys are columns of the Django model's database table.

    Returns
    -------
        OrderedDict mapping row id to row data dict of the ``name`` table.
    """
    query = getattr(models, name).objects.filter(**{f'{fk_name}_id__in': fk_ids})
    if fields_include is None:
        query = query.values()
    else:
        query = query.values(*fields_include.keys())
    return wrap_with_id_and_unflatten(query)


def serialize(name, get_result_values_map, fields_include=None):
    """
    Given a result_values_map (see :func:`wrap_with_id_and_unflatten`) mapping
    row ids of a table to the columns of that table only (no nested dicts),
    this produces a dict mapping row ids to dicts containing the tables columns' data,
    nested dicts, and nested arrays as defined by the table's one-to-one and
    one-to-many relationships.

    Parameters
    ----------
    name: str
        Name of the Orange Button object to serialize.

    get_result_values_map: Callable
        A Callable (e.g. function) that returns a result_values_map storing
        table rows.
        See :func:`wrap_with_id_and_unflatten` to see the form of result_values_map.

    fields_include: dict(str, Any)
        A (possibly nested) dict containing all of the columns of the named
        table and its related tables that should be included in the serialization.

    Returns
    -------
        OrderedDict mapping row ids to OrderedDicts.
    """
    if obit.get_schema_type(name) is obit.OBType.Element:
        return get_result_values_map(fields_include)

    # Collect all of the nested object and array names
    direct_objects = obit.objects_of_ob_object(name)
    direct_arrays = obit.arrays_of_ob_object(name)
    superclass_objects = tuple()
    superclass_arrays = tuple()
    superclass = obit.get_schema_superclass(name)
    if superclass is not None:
        superclass_objects = obit.objects_of_ob_object(superclass)
        superclass_arrays = obit.arrays_of_ob_object(superclass)
    all_objects = direct_objects + superclass_objects
    all_arrays = direct_arrays + superclass_arrays

    # filter what to serialize by fields_include
    # also, add to fields include the non-OB field database columns
    fields_include_all_arrays = OrderedDict()
    if fields_include is not None:
        all_objects = tuple(o for o in all_objects if o in fields_include)
        all_arrays = tuple((plural, s) for plural, s in all_arrays if plural in fields_include)
        fields_include = fields_include.copy()
        fields_include['id'] = ''  # the internal row id
        for o in all_objects:
            fields_include[f'{o}_id'] = ''  # one-to-one relations
        if superclass is not None:
            fields_include[f'{superclass.lower()}_ptr_id'] = ''  # multi-table inheritance one-to-one relation
        for plural, _ in all_arrays:  # arrays are one-to-many, and not referenced by this table, so separate them
            fields_include_all_arrays[plural] = fields_include[plural]
            del fields_include[plural]

    # get the rows passing the updated fields_include dict
    result_values_map = get_result_values_map(fields_include)

    # set to an empty OrderedDict for ease-of-use later when calling .get
    if fields_include is None:
        fields_include = OrderedDict()

    # Create a map of nested object names to their model ids
    object_values_map = {}
    for v in result_values_map.values():
        for o in all_objects:
            if o not in object_values_map:
                object_values_map[o] = []
            object_values_map[o].append(v[o]['id'])
        for plural, _ in all_arrays:
            v[plural] = []
        del v['id']
        if superclass is not None:
            del v[superclass.lower()]

    # Fetch all the nested object's models from the database
    for o, obj_ids in object_values_map.items():
        object_values_map[o] = serialize(  # serialize the nested object
            name=o,
            get_result_values_map=lambda fi: get_values_by_ids(o, obj_ids, fields_include=fi),
            fields_include=fields_include.get(o, None)
        )

    # Create a map of nested array names to their models from the database
    # Unlike objects, they are fetched by the parent models' ids
    # The parent model may be the parent name or the parent's superclass
    array_values_map = {}
    direct_array_singulars = tuple(singular for _, singular in direct_arrays)
    for plural, singular in all_arrays:
        fk_name = name
        if not (superclass is None or singular in direct_array_singulars):
            fk_name = superclass
        fields_include_array = fields_include_all_arrays.get(plural, [None])[0]
        if fields_include_array is not None:
            fields_include_array[f'{fk_name}_id'] = ''
        array_values_map[(plural, fk_name)] = serialize(  # serialize the nested array
            name=singular,
            get_result_values_map=lambda fi: get_values_by_fk_ids(singular, fk_name, result_values_map.keys(), fields_include=fi),
            fields_include=fields_include_array
        )

    # Substitute nested object ids for their values in the parent object
    for v in result_values_map.values():
        for o in all_objects:
            v[o] = object_values_map[o][v[o]['id']]

    # Substitute the default empty nested arrays with the actual arrays
    for (plural, fk_name), vs in array_values_map.items():
        for v in vs.values():
            fk_id = v[fk_name]['id']
            result_values_map[fk_id][plural].append(v)
            del v[fk_name]

    return result_values_map


def serialize_by_ids(name, ids, fields_include=None):
    """
    Wrapper for :func:`serialize` to help serialize Django models by their ids.

    Parameters
    ----------
    name: str
        Name of the Orange Button object to serialize.

    ids: Iterable(int)
        An iterable of row ids of the ``name`` table.

    fields_include: dict(str, Any)
        A (possibly nested) dict containing all of the columns of the named
        table and its related tables that should be included in the serialization.

    Returns
    -------
        OrderedDict mapping row ids to OrderedDicts.
    """
    return serialize(name, lambda fi: get_values_by_ids(name, ids, fields_include=fi), fields_include=fields_include)


def serialize_product_id_groups(groups):
    first_products = OrderedDict()
    first_product_ids = [i for i, _ in groups]
    for p in obit.get_schema_subclasses('Product'):
        first_products.update(serialize_by_ids(p, first_product_ids))
    for product_serialized, group_ids in zip(first_products.values(), [group for _, group in groups], strict=True):
        product_serialized['SubstituteProducts'] = list(serialize_by_ids('Product', group_ids, fields_include=OrderedDict(
            [(f, '') for f in itertools.chain(
                obit.OBElement('ProdCode').model_field_names(),
                obit.OBElement('ProdID').model_field_names(),
                obit.OBElement('ProdMfr').model_field_names(),
                obit.OBElement('ProdName').model_field_names(),
                obit.OBElement('ProdType').model_field_names(),
            )],
            Dimension=OrderedDict(Height_Value=''),
            ProdCertifications=[OrderedDict(CertificationDate_Value='')]
        )).values())
    return first_products


def get_edits(o):
    edits = models.Edit.objects.raw(
        """
        SELECT id, server_Edit.FieldName FROM server_Edit JOIN (
            SELECT FieldName, max(DateSubmitted) as DateSubmitted FROM server_Edit
            GROUP BY FieldName
        ) as latest_edits
        ON server_Edit.DateSubmitted=latest_edits.DateSubmitted
        AND server_Edit.FieldName=latest_edits.FieldName
        WHERE server_Edit.ModelName=%s
        AND server_Edit.InstanceID=%s
        AND server_Edit.Status=%s
        AND server_Edit.Type=%s;
        """,
        params=(
            o.__class__.__name__, o.id,
            models.Edit.StatusChoice.Pending.value,
            models.Edit.TypeChoice.Update.value
        )
    )
    return edits
