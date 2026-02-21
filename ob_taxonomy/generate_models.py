import ast
from functools import partial
import keyword
import itertools

from django.db import models
import ob_taxonomy.models as ob_models


def generate_django_enum_field(django_enum_name: str):
    return ast.Call(
        func=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='CharField', ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg='max_length', value=ast.Call(
                func=ast.Name(id='max', ctx=ast.Load()),
                args=[
                    ast.Call(
                        func=ast.Name(id='map', ctx=ast.Load()),
                        args=[
                            ast.Name(id='len', ctx=ast.Load()),
                            ast.Name(id=django_enum_name, ctx=ast.Load()),
                        ]
                    )
                ]
            )),
            ast.keyword(arg='choices', value=ast.Name(id=django_enum_name, ctx=ast.Load())),
            ast.keyword(arg='blank', value=ast.Constant(value=True)),
        ],
    )


def generate_django_enum_class(django_enum_name: str, enums: type[ob_models.OBItemTypeEnum | ob_models.OBItemTypeUnit]):
    return ast.ClassDef(
        name=django_enum_name,
        bases=[ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='TextChoices', ctx=ast.Load())],
        keywords=[],
        body=[
            ast.Assign(
                targets=[ast.Name(id=e.name if e.name not in keyword.kwlist else f'{e.name}_', ctx=ast.Store())],
                value=ast.Tuple(elts=[
                    ast.Constant(value=e.name),
                    ast.Call(
                        func=ast.Name(id='_'),
                        args=[ast.Constant(value=e.name if e.label == '' else e.label)]
                    ),
                ], ctx=ast.Load()),
            )
            for e in enums
        ],
        decorator_list=[],
    )


COMMON_KWARGS = dict(blank=True, null=True)
FLOAT_FIELD_KWARGS = COMMON_KWARGS
CHAR_FIELD_KWARGS = dict(blank=True)
SCHEMA_NAME_FIELD_CONF = dict(
    FileFolderURL=dict(func=partial(models.URLField, **CHAR_FIELD_KWARGS)),
    HomePhone=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=15)),
    MobilePhone=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=15)),
    ProdCode=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, null=True, max_length=50, unique=True, editable=False, db_index=True)),
    TaxID=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=20)),
    WorkPhone=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=15)),
    URL=dict(func=partial(models.URLField, **CHAR_FIELD_KWARGS)),
)
OB_ITEM_TYPE_FIELD_CONF = dict(
    AreaItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    BooleanItemType=dict(func=partial(models.BooleanField, **COMMON_KWARGS)),
    DateItemType=dict(func=partial(models.DateField, **COMMON_KWARGS)),
    DateTimeItemType=dict(func=partial(models.DateTimeField, **COMMON_KWARGS)),
    DecimalItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    DecimalPercentItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    DurationItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    ElectricCurrentItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    EnergyItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    LegalEntityIdentifierItemType=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=20)),
    LengthItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    MassItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    IntegerItemType=dict(func=partial(models.IntegerField, **COMMON_KWARGS)),
    PlaneAngleItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    PowerItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    StringItemType=dict(func=partial(models.CharField, **CHAR_FIELD_KWARGS, max_length=500)),
    TempCoefficientItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    TemperatureItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
    UUIDItemType=dict(
        ast=ast.Call(
            func=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='UUIDField', ctx=ast.Load()),
            args=[],
            keywords=[
                ast.keyword(arg='unique', value=ast.Constant(value=True)),
                ast.keyword(arg='editable', value=ast.Constant(value=False)),
                ast.keyword(arg='db_index', value=ast.Constant(value=True)),
                ast.keyword(arg='default', value=ast.Attribute(value=ast.Name(id='uuid', ctx=ast.Load()), attr='uuid4', ctx=ast.Load())),
            ],
        ),
    ),
    VoltageItemType=dict(func=partial(models.FloatField, **FLOAT_FIELD_KWARGS)),
)
SCHEMA_FIELD_CONF_FUNCS = dict(
    IDsAreUUIDs=lambda name: OB_ITEM_TYPE_FIELD_CONF['UUIDItemType'] if name.endswith('ID') else None,
)


def field_conf_to_django_field(field_info):
    if (field := field_info.get('func')) is not None:
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr=field.func.__name__, ctx=ast.Load()),
            args=[ast.Constant(value=v) for v in field.args],
            keywords=[ast.keyword(arg=k, value=ast.Constant(value=v)) for k, v in field.keywords.items()],
        )
    elif 'ast' in field_info:
        return field_info['ast']
    else:
        raise ValueError('field_info entry must be a dict with one of "func" or "ast" keys.')


def generate_ob_element_fields(ob_element: ob_models.OBElement):
    fields = []
    if ob_element.item_type.enums.exists() and ob_element.item_type.name != 'UUIDItemType':
        value_field = generate_django_enum_field(f'{ob_element.item_type.name}Enum')
        fields.append(ast.Assign(
            targets=[ast.Name(id=f'{ob_element.name}_Value', ctx=ast.Store())],
            value=value_field,
        ))
    else:
        if ob_element.item_type.units.exists():
            unit_field = generate_django_enum_field(f'{ob_element.item_type.name}Unit')
            fields.append(ast.Assign(
                targets=[ast.Name(id=f'{ob_element.name}_Unit', ctx=ast.Store())],
                value=unit_field,
            ))
        field_info = SCHEMA_NAME_FIELD_CONF.get(ob_element.name)
        if field_info is None:
            for func in SCHEMA_FIELD_CONF_FUNCS.values():
                field_info = func(ob_element.name)
                if field_info is not None:
                    break
            else:
                field_info = OB_ITEM_TYPE_FIELD_CONF[ob_element.item_type.name]
        value_field = field_conf_to_django_field(field_info)
        fields.append(ast.Assign(
            targets=[ast.Name(id=f'{ob_element.name}_Value', ctx=ast.Store())],
            value=value_field,
        ))
    return fields


def generate_ob_element_table(ob_element: ob_models.OBElement):
    fields = generate_ob_element_fields(ob_element)
    for f in fields:
        f.targets[0].id = f.targets[0].id.split('_')[-1]
    return ast.ClassDef(
        name=ob_element.name,
        bases=[ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='Model', ctx=ast.Load())],
        keywords=[],
        body=fields,
        decorator_list=[],
    )


def build_django_enum_class_context(ob_item_type: ob_models.OBItemType, context):
    if ob_item_type.enums.exists() and ob_item_type.name != 'UUIDItemType':
        class_name = f'{ob_item_type.name}Enum'
        enums = ob_item_type.enums.all()
    elif ob_item_type.units.exists():
        class_name = f'{ob_item_type.name}Unit'
        enums = ob_item_type.units.all()
    else:
        return
    context['django_enum_classes'][class_name] = (class_name, enums.order_by('name'))


def build_ob_object_context(ob_object: ob_models.OBObject, context, composes=False):
    if ob_object.name in context['comprisal_objects'] or ob_object.name in context['objects']:
        return
    if ob_object.comprises.exists():
        if ob_object.comprises.through.objects.exclude(method='allOf').exists():
            raise ValueError(f'Cannot generate Django model for {ob_object!r} because only the comprisal method "allOf" is currently supported.')
        if ob_object.comprises.count() > 1:
            raise ValueError(f'Cannot generate Django model for {ob_object!r} because the comprisal of multiple OBObjects is not currently supported.')
        comprisal = ob_object.comprises.first()
        build_ob_object_context(comprisal, context, composes=True)
        context['comprisal_objects'][comprisal.name] = comprisal
    for ob_element in ob_object.properties.all():
        build_django_enum_class_context(ob_element.item_type, context)
    for nested_object in ob_object.nested_objects.all():
        if nested_object.name not in context['objects']:
            build_ob_object_context(nested_object, context)
    for element_array in ob_object.element_arrays.all():
        build_django_enum_class_context(element_array.items.item_type, context)
        context['element_arrays'][element_array.items.name] = element_array.items
    for object_array in ob_object.object_arrays.all():
        build_ob_object_context(object_array.items, context)
    if not composes:
        context['objects'][ob_object.name] = ob_object


def generate_foreign_key(name):
    return ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store())],
        value=ast.Call(
            func=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='OneToOneField', ctx=ast.Load()),
            args=[ast.Constant(value=name)],
            keywords=[
                ast.keyword(arg='on_delete',
                            value=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='CASCADE', ctx=ast.Load())),
            ]
        )
    )


def generate_manytomany(name, name_other):
    return ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store())],
        value=ast.Call(
            func=ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='ManyToManyField', ctx=ast.Load()),
            args=[ast.Constant(value=name_other)],
            keywords=[]
        )
    )


def generate_ob_object(ob_object: ob_models.OBObject):
    if ob_object.comprises.exists():
        bases = [ast.Name(id=ob_object.comprises.first().name)]
    else:
        bases = [ast.Attribute(value=ast.Name(id='models', ctx=ast.Load()), attr='Model', ctx=ast.Load())]
    klass = ast.ClassDef(
        name=ob_object.name,
        bases=bases,
        keywords=[],
        body=[],
        decorator_list=[],
    )
    for ob_element in ob_object.properties.all().order_by('name'):
        klass.body.extend(generate_ob_element_fields(ob_element))
    for nested_object in ob_object.nested_objects.all().order_by('name'):
        klass.body.append(generate_foreign_key(nested_object.name))
    for array in itertools.chain(
        ob_object.element_arrays.all().order_by('name'),
        ob_object.object_arrays.all().order_by('name')
    ):
        klass.body.append(generate_manytomany(array.name, array.items.name))
    return klass


def generate_model_module(ob_objects):
    context = dict(
        django_enum_classes={},
        comprisal_objects={},
        objects={},
        element_arrays={},
    )
    for ob_object in ob_objects:
        build_ob_object_context(ob_object, context)
    generators = dict(
        django_enum_classes=lambda v: generate_django_enum_class(*v),
        comprisal_objects=generate_ob_object,
        objects=generate_ob_object,
        element_arrays=generate_ob_element_table,
    )
    for (k, v), g in zip(context.items(), generators.values()):
        model_names = v.keys()
        if k != 'comprisal_objects':
            model_names = sorted(model_names)
        context[k] = [g(v[kk]) for kk in model_names]
    tree = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name='uuid', asname=None)]),  # user should be responsible for these imports, i.e., required by django field default keyword arguments
            ast.ImportFrom(module='django.db', names=[ast.alias(name='models')], level=0),
            ast.ImportFrom(module='django.utils.translation', names=[ast.alias(name='gettext_lazy', asname='_')], level=0),
            *itertools.chain.from_iterable(context.values())
        ],
        type_ignores=[],
    )
    tree = ast.fix_missing_locations(tree)
    return tree


def test():
    tree = generate_model_module(ob_models.OBObject.objects.filter(name__in=[
        'ProdBattery',
        # 'ProdCell',
        # 'ProdCombiner',
        # 'ProdEnergyStorageSystem',
        # 'ProdGlazing',
        # 'ProdInverter',
        # 'ProdMeter',
        'ProdModule',
        # 'ProdOptimizer',
        # 'ProdWire',
    ]))
    print(ast.unparse(tree))
