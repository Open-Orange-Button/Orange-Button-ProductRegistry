from collections import OrderedDict

from rest_framework import serializers
import flatten_json

from server import models
from server import ob_item_types as obit


def get_values_by_ids(model_name, ids):
    return OrderedDict([
        (o['id'], flatten_json.unflatten_list(o, '_'))
        for o in getattr(models, model_name).objects.filter(id__in=ids).values()
    ])


def serialize_products(ids):
    prodbattery_map = get_values_by_ids('ProdBattery', ids)
    objects_1to1 = obit.objects_of_ob_object('ProdBattery') + obit.objects_of_ob_object('Product')
    objects_1to1_ids_map = {}
    product_objects_1toM = obit.arrays_of_ob_object('Product')
    product_objects_1toM_ids_map = {plural: get_values_by_ids(singular, prodbattery_map.keys()) for plural, singular in product_objects_1toM}
    for v in prodbattery_map.values():
        for o in objects_1to1:
            if o not in objects_1to1_ids_map:
                objects_1to1_ids_map[o] = []
            objects_1to1_ids_map[o].append(v[o]['id'])
    for o, v in objects_1to1_ids_map.items():
        objects_1to1_ids_map[o] = get_values_by_ids(o, v)
    for o in prodbattery_map.values():
        for o_1to1 in objects_1to1:
            o[o_1to1] = objects_1to1_ids_map[o_1to1][o[o_1to1]['id']]
    product_objects_1toM = obit.arrays_of_ob_object('Product')
    for plural, os in product_objects_1toM_ids_map.items():
        for o in os.values():
            product_id = o['Product']['id']
            if plural not in prodbattery_map[product_id]:
                prodbattery_map[product_id][plural] = []
            prodbattery_map[product_id][plural].append(o)
    return prodbattery_map.values()


class SerializerMetaclass(serializers.SerializerMetaclass):
    def __new__(cls, name, bases, attrs):
        if name != 'Serializer':
            match obit.get_schema_type(name):
                case obit.OBType.Element:
                    e = obit.OBElement(name, use_primitive_names=True)
                    for p in e.primitives():
                        attrs[p.name] = serializers.SerializerMethodField()
                        attrs[f'get_{p.name}'] = lambda _, obj: getattr(obj, p.name)
                case _:
                    cls.add_ob_elements(name, attrs)
                    cls.add_ob_objects(name, attrs)
                    cls.add_ob_arrays(name, attrs)
                    cls.add_superclass_info(name, attrs)
                    cls.define_to_representation(name, attrs)
        return super().__new__(cls, name, bases, attrs)

    @classmethod
    def add_ob_elements(cls, name, attrs):
        elements = attrs.get('ob_elements', None)
        if elements is None:
            elements = obit.elements_of_ob_object(name)
        for e in elements.values():
            attrs[e.name] = serializers.SerializerMethodField()
            attrs[f'get_{e.name}'] = cls._ob_element_serializer(e)

    @classmethod
    def _ob_element_serializer(cls, e: obit.OBElement):
        primitives = e.primitives()
        field_pairs = [(p.name, e.model_field_name(p)) for p in primitives]

        def get_ob_element(self, o):
            data = OrderedDict()
            for p, f in field_pairs:
                data[p] = getattr(o, f)
                if self.context.get('unconfirmed_edits', False):
                    data[p] = self.context['edits'].get(f, data[p])
            return data
        return get_ob_element

    @classmethod
    def add_ob_objects(cls, name, attrs):
        objects = attrs.get('ob_objects', None)
        if objects is None:
            objects = obit.objects_of_ob_object(name)
        for o in objects:
            attrs[o] = serializers.SerializerMethodField()
            attrs[f'get_{o}'] = cls._ob_object_serializer(o)

    @classmethod
    def _ob_object_serializer(cls, obj_name):
        serializer = eval(obj_name, globals(), locals())

        def get_ob_object(self, o):
            self.context.pop('edits', None)
            return serializer(getattr(o, obj_name), context=self.context).data

        return get_ob_object

    @classmethod
    def add_ob_arrays(cls, name, attrs):
        arrays = attrs.get('ob_arrays', None)
        if arrays is None:
            arrays = obit.arrays_of_ob_object(name)
        for plural, singular in arrays:
            attrs[plural] = serializers.SerializerMethodField()
            attrs[f'get_{plural}'] = cls._ob_array_serializer(singular)

    @classmethod
    def _ob_array_serializer(cls, array_name_singular):
        serializer = eval(array_name_singular, globals(), locals())
        src = f'{array_name_singular.lower()}_set'

        def get_ob_array(self, o):
            context = self.context.copy()
            context.pop('unconfirmed_edits', None)
            return serializer(getattr(o, src), many=True, context=self.context).data

        return get_ob_array

    @classmethod
    def add_superclass_info(cls, name, attrs):
        if (sc := obit.get_schema_superclass(name)) is not None:
            attrs['superclass_serializer'] = eval(sc, globals(), locals())
        else:
            attrs['superclass_serializer'] = None

    @classmethod
    def define_to_representation(cls, name, attrs):
        serialize = None
        if len(subclasses := obit.get_schema_subclasses(name)) > 0:
            def serialize_as_superclass(self, o):
                self.context['called_by_superclass'] = True
                kwargs = dict(context=self.context)
                if isinstance(o, OrderedDict):
                    return o  # DRF tries to serialize the POST data too
                superclass = super(self.__class__, self).to_representation(o)
                for m in subclasses:
                    if (p := getattr(o, m.lower(), None)) is not None:
                        subclass = eval(m, globals(), locals())(p, **kwargs).data
                        subclass.update(superclass)
                        return subclass
                return superclass
            serialize = serialize_as_superclass
        else:
            def serialize_as_maybe_subclass(self, o):
                if isinstance(o, OrderedDict):
                    return o  # DRF tries to serialize POST request data in response
                if not (self.superclass_serializer is None or self.context.pop('called_by_superclass', False)):
                    return self.superclass_serializer(getattr(o, o.__class__._meta.pk.name)).data
                return super(self.__class__, self).to_representation(o)
            serialize = serialize_as_maybe_subclass

        def to_representation(self, o):
            if isinstance(o, OrderedDict):
                return o  # DRF tries to serialize POST request data in response
            if self.context.get('unconfirmed_edits', False):
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
                self.context['edits'] = {e.FieldName: e.FieldValue for e in edits}
            return serialize(self, o)
        attrs['to_representation'] = to_representation


class Serializer(serializers.Serializer, metaclass=SerializerMetaclass):
    pass


class FrequencyAC(Serializer):
    pass


class ACInput(Serializer):
    pass


class PowerACSurge(Serializer):
    pass


class ACOutput(Serializer):
    pass


class Location(Serializer):
    pass


class Address(Serializer):
    pass


class AlternativeIdentifier(Serializer):
    pass


class Contact(Serializer):
    pass


class MPPT(Serializer):
    pass


class DCInput(Serializer):
    pass


class PowerDCPeak(Serializer):
    pass


class DCOutput(Serializer):
    pass


class Firmware(Serializer):
    pass


class CertificationAgency(Serializer):
    pass


class Dimension(Serializer):
    pass


class InverterEfficiencyCECTestResult(Serializer):
    pass


class InverterEfficiency(Serializer):
    pass


class Package(Serializer):
    pass


class ProdCertification(Serializer):
    pass


class ProdInstruction(Serializer):
    pass


class ProdSpecification(Serializer):
    pass


class Warranty(Serializer):
    pass


class ModuleElectRating(Serializer):
    pass


class Product(Serializer):
    pass


class ProdBattery(Serializer):
    pass


class ProdCell(Serializer):
    pass


class ProdCombiner(Serializer):
    pass


class ProdEnergyStorageSystem(Serializer):
    pass


class ProdGlazing(Serializer):
    pass


class ProdInverter(Serializer):
    pass


class ProdMeter(Serializer):
    pass


class ProdModule(Serializer):
    pass


class ProdName(Serializer):
    pass


class ProdOptimizer(Serializer):
    pass


class ProdWire(Serializer):
    pass
