import enum
import json
import re
import uuid
from pathlib import Path
from typing import Iterable, Tuple
from dataclasses import dataclass

from django.db import models
from django.core import validators

from django_mysql import models as mysql_models


NAME_LEN = 100
STR_LEN = 500
URL_LEN = 1000
TIME_STR_LEN = 100
DECIMAL_PLACES = 20
DECIMAL_MAX_DIGITS = DECIMAL_PLACES * 2
OB_TAXONOMY_FILEPATH = Path(__file__).parent / 'references' / 'Master-OB-OpenAPI.json'


def load_ob_taxonomy():
    with open(OB_TAXONOMY_FILEPATH) as f:
        return json.load(f)


OB_TAXONOMY = load_ob_taxonomy()


class TaxonomyElement(enum.Enum):
    Boolean = 'TaxonomyElementBoolean'
    Integer = 'TaxonomyElementInteger'
    Number = 'TaxonomyElementNumber'
    String = 'TaxonomyElementString'


class Primitive(enum.Enum):
    Decimals = enum.auto()
    EndTime = enum.auto()
    Precision = enum.auto()
    StartTime = enum.auto()
    Unit = enum.auto()
    Value = enum.auto()


class OBType(enum.Enum):
    Primitive = enum.auto()
    Element = enum.auto()
    Object = enum.auto()
    Array = enum.auto()


ItemTypeName = enum.Enum('ItemTypeName', {n: n for n in OB_TAXONOMY['x-ob-item-types']})


@dataclass(frozen=True)
class ItemType:
    name: ItemTypeName
    description: str


@dataclass(frozen=True)
class ItemTypeValue:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class Enum(ItemTypeValue):
    pass


@dataclass(frozen=True)
class Unit(ItemTypeValue):
    pass


@dataclass(frozen=True)
class ItemTypeEnum(ItemType):
    values: Tuple[ItemTypeValue]


@dataclass(frozen=True)
class ItemTypeUnit(ItemType):
    values: Tuple[ItemTypeValue]


@dataclass(frozen=True)
class ItemTypeGroup:
    type: str
    description: str
    group: Tuple[str]


@dataclass
class OBElement:
    name: str
    description: str
    superclass: str
    item_type: ItemType
    item_type_group: ItemTypeGroup

    def __init__(self, name, use_primitive_names=False, **Value_opts):
        allOf = OB_TAXONOMY['components']['schemas'][name]
        details = allOf['allOf'][1]

        self.name = name
        self.description = details['description']
        self.superclass = TaxonomyElement(get_schema_superclass(name))
        self.item_type = json_to_item_type(details['x-ob-item-type'])
        self.item_type_group = json_to_item_type_group(details['x-ob-item-type-group'])
        self.use_primitive_names = use_primitive_names
        self.Value_opts = Value_opts

    @property
    def grouped_item_type(self):
        if self.item_type_group is None:
            return self.item_type
        kwargs = dict(
            name=self.item_type.name,
            description=self.item_type.description
        )
        if self.item_type_has_enums or self.item_type_has_units:
            kwargs['values'] = tuple(v for v in self.item_type.values if v.id in self.item_type_group.group)
        return self.item_type.__class__(**kwargs)

    @property
    def item_type_has_enums(self):
        return self._item_type_has_values(ItemTypeEnum)

    @property
    def item_type_has_units(self):
        return self._item_type_has_values(ItemTypeUnit)

    def primitives(self):
        match self.superclass:
            case TaxonomyElement.Boolean:
                return self._boolean_fields()
            case TaxonomyElement.Integer:
                return self._integer_fields()
            case TaxonomyElement.Number:
                return self._number_fields()
            case TaxonomyElement.String:
                return self._string_fields()

    def model_fields(self):
        return {self.model_field_name(p): self._primitive_field(p)
                for p in self.primitives()}

    def model_field_name(self, p: Primitive):
        if self.use_primitive_names:
            return p.name
        return f'{self.name}_{p.name}'

    def verbose_model_field_name(self, p: Primitive):
        if self.use_primitive_names:
            return p.name
        return f'{self.name} {p.name}'

    def _item_type_has_values(self, item_type_class):
        nonempty_item_type_group = self.item_type_group is None or len(self.item_type_group.group) > 0
        return (
            self.item_type.__class__ is item_type_class
            and len(self.item_type.values) > 0
            and nonempty_item_type_group
        )

    def _boolean_fields(self):
        return [Primitive.EndTime, Primitive.StartTime, Primitive.Value]

    def _integer_fields(self):
        fields = [Primitive.EndTime, Primitive.StartTime, Primitive.Value]
        if self.item_type_has_units:
            fields.append(Primitive.Unit)
        return fields

    def _number_fields(self):
        fields = [Primitive.Decimals, Primitive.EndTime, Primitive.Precision,
                  Primitive.StartTime, Primitive.Value]
        if self.item_type_has_units:
            fields.append(Primitive.Unit)
        return fields

    def _string_fields(self):
        return [Primitive.EndTime, Primitive.StartTime, Primitive.Value]

    def _primitive_field(self, primitive: Primitive):
        match primitive:
            case Primitive.Decimals:
                return self._Decimals_field()
            case Primitive.EndTime:
                return self._EndTime_field()
            case Primitive.Precision:
                return self._Precision_field()
            case Primitive.StartTime:
                return self._StartTime_field()
            case Primitive.Unit:
                return self._Unit_field()
            case Primitive.Value:
                return self._Value_field()

    def _Decimals_field(self):
        return models.PositiveIntegerField(self.verbose_model_field_name(Primitive.Decimals),
                                   blank=True, null=True)

    def _EndTime_field(self):
        return models.DateTimeField(self.verbose_model_field_name(Primitive.EndTime),
                                    blank=True, null=True)

    def _Precision_field(self):
        return models.PositiveIntegerField(self.verbose_model_field_name(Primitive.Precision),
                                   blank=True, null=True)

    def _StartTime_field(self):
        return models.DateTimeField(self.verbose_model_field_name(Primitive.StartTime),
                                    blank=True, null=True)

    def _Unit_field(self):
        choices = [(v.id, v.label) for v in self.grouped_item_type.values]
        choices.append(('', ''))
        return mysql_models.EnumField(self.verbose_model_field_name(Primitive.Unit), choices=choices)

    def _Value_field(self):
        verbose_name = self.verbose_model_field_name(Primitive.Value)
        if (fc := self.Value_opts.pop('field_class', None)) is not None:
            return fc(verbose_name, **self.Value_opts)
        match self.superclass:
            case TaxonomyElement.Boolean:
                field_kwargs = dict(blank=True, null=True)
                field_kwargs.update(self.Value_opts)
                return models.BooleanField(verbose_name, **field_kwargs)
            case TaxonomyElement.Integer:
                return self._integer_field_by_item_type()
            case TaxonomyElement.Number:
                return self._number_field_by_item_type()
            case TaxonomyElement.String:
                return self._string_field_by_item_type()

    def _integer_field_by_item_type(self):
        verbose_name = self.verbose_model_field_name(Primitive.Value)
        match self.item_type.name:
            case ItemTypeName.DurationItemType:
                field_kwargs = dict(
                    validators=[
                        validators.MinValueValidator(0),
                    ],
                    blank=True, null=True
                )
                field_kwargs.update(self.Value_opts)
                return models.PositiveIntegerField(verbose_name, **field_kwargs)
            case _:
                field_kwargs = dict(blank=True, null=True)
                field_kwargs.update(self.Value_opts)
                return models.IntegerField(verbose_name, **field_kwargs)

    def _number_field_by_item_type(self):
        verbose_name = self.verbose_model_field_name(Primitive.Value)
        decimal_validators = [validators.DecimalValidator(DECIMAL_MAX_DIGITS, DECIMAL_PLACES)]
        match self.item_type.name:
            case ItemTypeName.DurationItemType | ItemTypeName.LengthItemType | ItemTypeName.MassItemType:
                decimal_validators.append(validators.MinValueValidator(0))
                field_kwargs = dict(
                    max_digits=DECIMAL_MAX_DIGITS,
                    decimal_places=DECIMAL_PLACES,
                    validators=decimal_validators,
                    blank=True, null=True
                )
                field_kwargs.update(self.Value_opts)
                return models.DecimalField(verbose_name, **field_kwargs)
            case ItemTypeName.PercentItemType:
                decimal_validators += [validators.MinValueValidator(0), validators.MaxValueValidator(100)]
                field_kwargs = dict(
                    max_digits=DECIMAL_MAX_DIGITS,
                    decimal_places=DECIMAL_PLACES,
                    validators=decimal_validators,
                    blank=True, null=True
                )
                field_kwargs.update(self.Value_opts)
                return models.DecimalField(verbose_name, **field_kwargs)
            case _:
                field_kwargs = dict(
                    max_digits=DECIMAL_MAX_DIGITS,
                    decimal_places=DECIMAL_PLACES,
                    validators=decimal_validators,
                    blank=True, null=True
                )
                field_kwargs.update(self.Value_opts)
                return models.DecimalField(verbose_name, **field_kwargs)

    def _string_field_by_item_type(self):
        verbose_name = self.verbose_model_field_name(Primitive.Value)
        match self.item_type.name:
            case ItemTypeName.DateItemType:
                field_kwargs = dict(blank=True, null=True)
                field_kwargs.update(self.Value_opts)
                return models.DateField(verbose_name, **field_kwargs)
            case ItemTypeName.UUIDItemType:
                field_kwargs = dict(
                    unique=True, editable=False, default=uuid.uuid4,
                    validators=[validators.RegexValidator(regex=re.compile('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'))]
                )
                field_kwargs.update(self.Value_opts)
                return models.UUIDField(verbose_name, **field_kwargs)
            case _:
                if self.item_type_has_enums:
                    choices = [(v.id, v.label) for v in self.grouped_item_type.values]
                    choices.append(('', ''))
                    return mysql_models.EnumField(verbose_name, choices=choices)
                field_kwargs = dict(blank=True, max_length=STR_LEN)
                field_kwargs.update(self.Value_opts)
                return models.CharField(verbose_name, **field_kwargs)


def json_to_item_type(name: str):
    it = OB_TAXONOMY['x-ob-item-types'][name]
    kwargs = dict(name=ItemTypeName(name), description=it['description'])
    match it:
        case {'enums': enums}:
            kwargs['values'] = tuple(Enum(id, v['label'], v['description'])
                                     for id, v in enums.items())
            return ItemTypeEnum(**kwargs)
        case {'units': units}:
            kwargs['values'] = tuple(Unit(id, v['label'], v['description'])
                                     for id, v in units.items())
            return ItemTypeUnit(**kwargs)
        case _:
            return ItemType(**kwargs)


def json_to_item_type_group(name: str):
    if name == '':
        return None
    itg = OB_TAXONOMY['x-ob-item-type-groups'][name]
    return ItemTypeGroup(itg['type'], itg['description'], tuple(itg['group']))


def get_ref_schema(ref: str):
    return ref.split('/')[-1]


def get_schema_superclass(name):
    match get_schema_defn(name):
        case {'allOf': [{'$ref': ref}, _]}:
            return get_ref_schema(ref)
        case _:
            return None


def get_schema_subclasses(name):
    return tuple(n for n in OB_TAXONOMY['components']['schemas']
                 if name == get_schema_superclass(n))


def get_schema_defn(name):
    return OB_TAXONOMY['components']['schemas'][name]


def is_primitive(name):
    return name in [p.name for p in Primitive]


def get_schema_type(name):
    if is_primitive(name):
        return OBType.Primitive
    match get_schema_defn(name):
        case {'allOf': [{'$ref': ref}, _]}:
            if get_ref_schema(ref) in tuple(t.value for t in TaxonomyElement):
                return OBType.Element
            return OBType.Object
        case {'type': 'object'}:
            return OBType.Object
        case {'type': 'array'}:
            return OBType.Array
        case _:
            raise ValueError(f'Unknown schema definition type: "{name}"')


def ob_object_properties(name):
    match get_schema_defn(name):
        case {'allOf': [{'$ref': _}, {'properties': props}]}:
            return props
        case {'type': 'object', 'properties': props}:
            return props
        case _:
            raise ValueError(f'Unknown OB object schema: "{name}"')


def elements_of_ob_object(name, **Element_Value_opts):
    return {n: OBElement(n, **Element_Value_opts.get(n, {}))
            for n in sorted(ob_object_properties(name))
            if get_schema_type(n) is OBType.Element}


def objects_of_ob_object(name):
    return tuple(n for n in sorted(ob_object_properties(name))
                 if get_schema_type(n) is OBType.Object)


def all_fields_of_ob_object(name, array_plurals=True, include_inherited=True):
    fields = (
        tuple(elements_of_ob_object(name).keys())
        + objects_of_ob_object(name)
        + tuple((plural if array_plurals else singular)
                for plural, singular in arrays_of_ob_object(name))
    )
    if include_inherited and (sc := get_schema_superclass(name)) is not None:
        fields += all_fields_of_ob_object(sc)
    return fields


def array_to_singular(name):
    return get_ref_schema(get_schema_defn(name)['items']['$ref'])


def arrays_of_ob_object(name):
    return tuple((n, array_to_singular(n))
                 for n in sorted(ob_object_properties(name))
                 if get_schema_type(n) is OBType.Array)


def ob_object_usage_as_array(name, user_schema_names):
    uses = []
    for uname in user_schema_names:
        for array_name in ob_object_properties(uname):
            match get_schema_defn(array_name):
                case {'type': 'array', 'items': {'$ref': ref}}:
                    if name == get_ref_schema(ref):
                        uses.append(uname)
                case _:
                    continue
    return tuple(sorted(uses))


def max_ob_object_element_name_length(*args: Iterable[str]):
    return max(len(n) for n in set().union(*(
        set(elements_of_ob_object(m)) for m in args
        if get_schema_type(m) is OBType.Object
    )))
