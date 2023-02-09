from collections import OrderedDict

import flatten_json

from server import models
from server import ob_item_types as obit


def get_values_by_ids(name, ids):
    return OrderedDict([
        (o['id'], flatten_json.unflatten(o, '_'))
        for o in getattr(models, name).objects.filter(id__in=ids).values()
    ])


def get_values_by_fk_ids(name, fk_name, fk_ids):
    return OrderedDict([
        (o['id'], flatten_json.unflatten(o, '_'))
        for o in getattr(models, name).objects.filter(**{f'{fk_name}_id__in': fk_ids}).values()
    ])


def serialize_by_ids(name, ids=None, result_values_map=None):
    if ids is not None:
        result_values_map = get_values_by_ids(name, ids)

    if obit.get_schema_type(name) is obit.OBType.Element:
        return result_values_map

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
        object_values_map[o] = serialize_by_ids(o, obj_ids)

    # Create a map of nested array names to their models from the database
    # Unlike objects, they are fetched by the parent models' ids
    # The parent model may be the parent name or the parent's superclass
    array_values_map = {}
    direct_array_singulars = tuple(singular for _, singular in direct_arrays)
    for plural, singular in all_arrays:
        fk_name = name
        if not (superclass is None or singular in direct_array_singulars):
            fk_name = superclass
        array_values_map[(plural, fk_name)] = serialize_by_ids(singular, result_values_map=get_values_by_fk_ids(singular, fk_name, result_values_map.keys()))

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
