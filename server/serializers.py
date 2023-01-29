from collections import OrderedDict

import flatten_json

from server import models
from server import ob_item_types as obit


def get_values_by_ids(name, ids):
    return OrderedDict([
        (o['id'], flatten_json.unflatten(o, '_'))
        for o in getattr(models, name).objects.filter(id__in=ids).values()
    ])


def serialize_by_ids(name, ids):
    result_values_map = get_values_by_ids(name, ids)
    if obit.get_schema_type(name) is obit.OBType.Element:
        return result_values_map
    objects = obit.objects_of_ob_object(name)
    arrays = obit.arrays_of_ob_object(name)
    superclass = obit.get_schema_superclass(name)
    if superclass is not None:
        objects += obit.objects_of_ob_object(superclass)
        arrays += obit.arrays_of_ob_object(superclass)
    object_values_map = {}
    for v in result_values_map.values():
        for o in objects:
            if o not in object_values_map:
                object_values_map[o] = []
            object_values_map[o].append(v[o]['id'])
        for plural, _ in arrays:
            v[plural] = []
        del v['id']
        if superclass is not None:
            del v[superclass.lower()]
    for o, ids in object_values_map.items():
        object_values_map[o] = serialize_by_ids(o, ids)
    array_values_map = {plural: serialize_by_ids(singular, result_values_map.keys()) for plural, singular in arrays}
    for v in result_values_map.values():
        for o in objects:
            v[o] = object_values_map[o][v[o]['id']]
    for plural, vs in array_values_map.items():
        fk_name = name if superclass is None else superclass
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
