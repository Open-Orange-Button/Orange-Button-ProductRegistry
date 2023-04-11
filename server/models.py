from collections import OrderedDict
import enum

from django.db import models
from django.core import validators
from django.contrib import auth

from django_mysql import models as mysql_models

import rest_framework

import server.ob_item_types as obit


@models.Field.register_lookup
class IContains(models.lookups.IContains):
    """
    Custom implementation of the ``icontains`` QuerySet lookup filter.
    """

    def as_sql(self, compiler, connection):
        """
        Return MySQL that matches lowercased values with a lowercased
        pattern string.

        The superclass claims to use ``ILIKE`` but keyword this does not exist
        in MySQL.
        """
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = (*lhs_params, *map(str.lower, rhs_params))
        return f'LOWER({lhs}) LIKE {rhs}', params


def get_all_ob_submodels(name):
    results = OrderedDict([(name, '')])
    for o in obit.objects_of_ob_object(name):
        results.update(get_all_ob_submodels(o))
    for _, singular in obit.arrays_of_ob_object(name):
        if obit.get_schema_type(singular) is obit.OBType.Object:
            results.update(get_all_ob_submodels(singular))
        else:
            results[singular] = ''
    return results


def get_ob_all_models():
    results = get_all_ob_submodels('Product')
    for p in obit.get_schema_subclasses('Product'):
        results.update(get_all_ob_submodels(p))
    return results


FOREIGN_KEY_KWARGS = dict(on_delete=models.DO_NOTHING)
OB_MODELS = tuple(get_ob_all_models().keys())
EDIT_MODELS = (
    'EditChar', 'EditDateTime', 'EditDecimal', 'EditPositiveInteger',
    'EditInteger', 'EditURL', 'EditUUID'
)


class ModelBase(models.base.ModelBase):
    def __new__(cls, name, bases, attrs, **kwargs):
        if name != 'Model':
            match obit.get_schema_type(name):
                case obit.OBType.Element:
                    e = obit.OBElement(name, use_primitive_names=True)
                    for field_name, field in e.model_fields().items():
                        attrs[field_name] = field
                case _:
                    cls.add_ob_elements(name, attrs)
                    cls.add_ob_objects(name, attrs)
            cls.add_ob_array_usages(name, attrs)
        return super().__new__(cls, name, bases, attrs, **kwargs)

    def add_ob_elements(name, attrs):
        elements = attrs.get('ob_elements', None)
        if elements is None:
            elements = obit.elements_of_ob_object(name)
            attrs['ob_elements'] = elements
        for e in elements.values():
            for field_name, field in e.model_fields().items():
                attrs[field_name] = field

    def add_ob_objects(name, attrs):
        objects = attrs.get('ob_objects', None)
        if objects is None:
            objects = obit.objects_of_ob_object(name)
        for o in objects:
            attrs[o] = models.OneToOneField(o, on_delete=models.DO_NOTHING)

    def add_ob_array_usages(name, attrs):
        user_schemas = [m for m in OB_MODELS
                        if obit.get_schema_type(m) is obit.OBType.Object]
        arrays = attrs.get('ob_array_usages', None)
        if arrays is None:
            arrays = obit.ob_object_usage_as_array(name, user_schemas)
        for a in arrays:
            attrs[a] = models.ForeignKey(a, **FOREIGN_KEY_KWARGS)


class Model(mysql_models.Model, metaclass=ModelBase):
    pass

    class Meta:
        abstract = True


class Dimension(Model):
    pass


class Product(Model):
    ob_elements = obit.elements_of_ob_object(
        'Product',
        FileFolderURL=dict(
            max_length=obit.URL_LEN,
            validators=[validators.URLValidator()]
        ),
        ProdCode=dict(unique=True, validators=[])  # should have regex validation
    )


class CertificationAgency(Model):
    pass


class Location(Model):
    pass


class DCInput(Model):
    ob_elements = obit.elements_of_ob_object(
        'DCInput',
        MPPTNumber=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        )
    )


class DCOutput(Model):
    pass


class ProdBattery(Product):
    pass


class ProdCell(Model):
    pass


class ProdCombiner(Product):
    pass


class ProdEnergyStorageSystem(Product):
    pass


class InverterEfficiency(Model):
    pass


class ProdMeter(Product):
    pass


class ProdGlazing(Model):
    ob_elements = obit.elements_of_ob_object(
        'ProdGlazing',
        FileFolderURL=dict(
            max_length=obit.URL_LEN,
            validators=[validators.URLValidator()]
        )
    )


class ProdModule(Product):
    ob_elements = obit.elements_of_ob_object(
        'ProdModule',
        BypassDiodeQuantity=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        ),
        CellStringsParallelQuantity=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        ),
        CellCount=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        ),
        CellsInSeries=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        )
    )


class ProdInverter(Product):
    pass


class ModuleElectRating(Model):
    pass


class ProdName(Model):
    pass


class ProdOptimizer(Product):
    pass


class ProdWire(Product):
    pass


class AlternativeIdentifier(Model):
    ob_elements = obit.elements_of_ob_object(
        'AlternativeIdentifier',
        Identifier=dict(unique=True)
    )


class MPPT(Model):
    ob_elements = obit.elements_of_ob_object(
        'MPPT',
        MPPTInputStrings=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        )
    )


class Warranty(Model):
    ob_elements = obit.elements_of_ob_object(
        'Warranty',
        FileFolderURL=dict(
            max_length=obit.URL_LEN,
            validators=[validators.URLValidator()]
        ),
        WarrantyID=dict(editable=True, blank=True, default='')
    )


class Package(Model):
    pass


class ProdInstruction(Model):
    pass


class ProdSpecification(Model):
    pass


class ProdCertification(Model):
    ob_elements = obit.elements_of_ob_object(
        'ProdCertification',
        FileFolderURL=dict(
            max_length=obit.URL_LEN,
            validators=[validators.URLValidator()]
        )
    )


class Address(Model):
    pass


class Contact(Model):
    ob_elements = obit.elements_of_ob_object(
        'Contact',
        URL=dict(validators=[validators.URLValidator()])
    )


class Firmware(Model):
    pass


class PowerDCPeak(Model):
    pass


class FrequencyAC(Model):
    pass


class InverterEfficiencyCECTestResult(Model):
    pass


class ACInput(Model):
    pass


class ACOutput(Model):
    ob_elements = obit.elements_of_ob_object(
        'ACOutput',
        InterconnectionLineCount=dict(
            field_class=models.PositiveIntegerField,
            validators=[validators.MinValueValidator(0)],
            blank=True, null=True
        )
    )


class PowerACSurge(Model):
    pass


class User(auth.models.AbstractUser):
    pass


class Edit(models.Model):
    StatusChoice = enum.Enum('Statuses', {s: s[0] for s in ('Approved', 'Pending', 'Rejected')})
    TypeChoice = enum.Enum('Types', {t: t[0] for t in ('Addition', 'Update', 'Deletion')})
    ModelName = mysql_models.EnumField(choices=[(m, m) for m in OB_MODELS])
    InstanceID = models.PositiveBigIntegerField()  # to match BigAutoField
    FieldName = models.CharField(max_length=obit.max_ob_object_element_name_length(*OB_MODELS))
    Status = mysql_models.EnumField(choices=[(s.value, s.name) for s in StatusChoice])
    Type = mysql_models.EnumField(choices=[(t.value, t.name) for t in TypeChoice])
    DataSourceComment = models.CharField(max_length=obit.STR_LEN, blank=True)
    DateSubmitted = models.DateTimeField()
    DateApproved = models.DateTimeField(blank=True, null=True)
    DateEffective = models.DateTimeField(blank=True, null=True)
    SubmittedBy = models.ForeignKey(auth.get_user_model(), related_name='edits_submittedby_set', on_delete=models.DO_NOTHING)
    ApprovedBy = models.ForeignKey(auth.get_user_model(), related_name='edits_approvedby_set', on_delete=models.DO_NOTHING, blank=True, null=True)

    @property
    def FieldValue(self):
        return self._subclass().FieldValue

    @property
    def FieldValueOld(self):
        return self._subclass().FieldValueOld

    def _subclass(self):
        for m in EDIT_MODELS:
            if (s := getattr(self, m.lower(), None)) is not None:
                return s


class EditChar(Edit):
    FieldValue = models.CharField(max_length=obit.STR_LEN, blank=True)
    FieldValueOld = models.CharField(max_length=obit.STR_LEN, blank=True)


class EditDateTime(Edit):
    FieldValue = models.DateTimeField(blank=True, null=True)
    FieldValueOld = models.DateTimeField(blank=True, null=True)


class EditDecimal(Edit):
    FieldValue = models.DecimalField(max_digits=obit.DECIMAL_MAX_DIGITS,
                                     decimal_places=obit.DECIMAL_PLACES,
                                     blank=True, null=True)
    FieldValueOld = models.DecimalField(max_digits=obit.DECIMAL_MAX_DIGITS,
                                        decimal_places=obit.DECIMAL_PLACES,
                                        blank=True, null=True)


class EditPositiveInteger(Edit):
    FieldValue = models.PositiveIntegerField(blank=True, null=True)
    FieldValueOld = models.PositiveIntegerField(blank=True, null=True)


class EditInteger(Edit):
    FieldValue = models.IntegerField(blank=True, null=True)
    FieldValueOld = models.IntegerField(blank=True, null=True)


class EditURL(Edit):
    FieldValue = models.CharField(max_length=obit.URL_LEN, blank=True)
    FieldValueOld = models.CharField(max_length=obit.URL_LEN, blank=True)


class EditUUID(Edit):
    FieldValue = models.UUIDField(blank=True)
    FieldValueOld = models.UUIDField(blank=True)


class APIToken(rest_framework.authtoken.models.Token):
    expires = models.DateTimeField(default=None, blank=True, null=True)
    is_active = models.BooleanField(default=True, blank=True)
