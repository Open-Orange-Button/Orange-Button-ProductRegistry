from django.db import models
from django.utils.translation import gettext_lazy as _


class OBPrimitive(models.Model):
    name = models.CharField(max_length=len('ValueArrayBoolean'), unique=True)
    description = models.CharField(max_length=len('Decimals of the instance element. Decimal is the number of meaningful digits relative to a decimal point. For example, 1.32 may have a Decimal value of 2, where 1100 may have a Decimal value of -2.'))
    is_array = models.BooleanField()

    def __str__(self):
        return self.name


class OBTaxonomyElement(models.Model):
    name = models.CharField(max_length=len('TaxonomyElementArrayBoolean'), unique=True)
    primitives = models.ManyToManyField(OBPrimitive)

    def __str__(self):
        return self.name


class OBItemTypeEnum(models.Model):
    name = models.CharField(max_length=len('SuretyEngineeringProcurementConstructionPaymentBondWithSolarModuleSupplierSublimitsAsDualObligee'), unique=True)
    label = models.CharField(max_length=len('AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent'))
    description = models.CharField(max_length=len('A type of digital identifier that enables individuals or entities to create and control their own identity without relying on a centralized authority. DIDs are designed to be self-sovereign, meaning they can be created, updated, and managed directly by their owners, independent of third-party intermediaries.  DIDs are typically implemented using distributed ledger technologies (blockchains) or other decentralized networks, which provide a secure and tamper-proof environment for storing and managing identity-related information. Each DID resolves to a DID document, which contains cryptographic keys, authentication methods, and other metadata necessary for verifying ownership and facilitating trusted interactions between parties. This approach promotes privacy, security, and user control over personal data in digital identity systems.'))
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'label'], name='unique_enum_name_and_label'),
        ]

    def __str__(self):
        return f'{self.label} ({self.name})'


class OBItemTypeUnit(models.Model):
    name = models.CharField(max_length=len('Monetary_per_Monetary'))
    label = models.CharField(max_length=len('Bosnia and Herzegovina convertible mark'))
    description = models.CharField(max_length=len('The kelvin is a unit of measure for temperature based upon an absolute scale. It is one of the seven base units in the International System of Units (SI) and is assigned the unit symbol K. The Kelvin scale is an absolute, thermodynamic temperature scale using as its null point absolute zero, the temperature at which all thermal motion ceases in the classical description of thermodynamics. The kelvin is defined as the fraction  1⁄273.16 of the thermodynamic temperature of the triple point of water (exactly 0.01 °C or 32.018 °F). In other words, it is defined such that the triple point of water is exactly 273.16 K.'))
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'label'], name='unique_unit_name_and_label'),
        ]

    def __str__(self):
        return f'{self.label} ({self.name})'


class OBItemType(models.Model):
    name = models.CharField(max_length=len('PreventiveMaintenanceTaskStatusItemType'), unique=True)
    description = models.CharField(max_length=len('A type of digital identifier that enables individuals or entities to create and control their own identity without relying on a centralized authority. DIDs are designed to be self-sovereign, meaning they can be created, updated, and managed directly by their owners, independent of third-party intermediaries.  DIDs are typically implemented using distributed ledger technologies (blockchains) or other decentralized networks, which provide a secure and tamper-proof environment for storing and managing identity-related information. Each DID resolves to a DID document, which contains cryptographic keys, authentication methods, and other metadata necessary for verifying ownership and facilitating trusted interactions between parties. This approach promotes privacy, security, and user control over personal data in digital identity systems.'))
    enums = models.ManyToManyField(OBItemTypeEnum)
    units = models.ManyToManyField(OBItemTypeUnit)

    def __str__(self):
        return self.name


class OBItemTypeGroup(models.Model):
    name = models.CharField(max_length=len('OBElectricalEnergy'), unique=True)
    description = models.CharField(max_length=len('Restriction of MassItemType to only units of mass: g, kg, t, kt, Mt, Gt'))
    item_type = models.ForeignKey(OBItemType, on_delete=models.DO_NOTHING)
    enums = models.ManyToManyField(OBItemTypeEnum)
    units = models.ManyToManyField(OBItemTypeUnit)

    def __str__(self):
        return self.name


class OBElement(models.Model):
    name = models.CharField(max_length=len('TemperatureCoefficientShortCircuitCurrent'), unique=True)
    description = models.CharField(max_length=len('A product code is a standardized, unique human-readable identifier that is compact, and can be easily parsed. It consists of an entity code concatenated to a product specific identification string, separated by a hyphen. The format of a product code is: [EntityCode]-[ProductString], e.g., “HANWH-Q_PEAK_DUO_BLK_G10__AC_365”. A product string is comprised of upper-case letters, numbers, and underscores. Any character that is not a letter or number is a special character and will be replaced by an underscore. All letter characters will be upper case. To avoid clashes between identical product codes, an additional hyphen and an integer 1, 2, 3, ..., is appended, e.g. {ProdCode}-{incremental number}'))
    taxonomy_element = models.ForeignKey(OBTaxonomyElement, on_delete=models.DO_NOTHING)
    item_type = models.ForeignKey(OBItemType, on_delete=models.DO_NOTHING)
    item_type_group = models.ForeignKey(OBItemTypeGroup, on_delete=models.DO_NOTHING, null=True)

    def __str__(self):
        return self.name


class OBObject(models.Model):
    name = models.CharField(max_length=len('TemperatureCoefficientShortCircuitCurrent'), unique=True)
    description = models.CharField(max_length=len('A product code is a standardized, unique human-readable identifier that is compact, and can be easily parsed. It consists of an entity code concatenated to a product specific identification string, separated by a hyphen. The format of a product code is: [EntityCode]-[ProductString], e.g., “HANWH-Q_PEAK_DUO_BLK_G10__AC_365”. A product string is comprised of upper-case letters, numbers, and underscores. Any character that is not a letter or number is a special character and will be replaced by an underscore. All letter characters will be upper case. To avoid clashes between identical product codes, an additional hyphen and an integer 1, 2, 3, ..., is appended, e.g. {ProdCode}-{incremental number}'))
    properties = models.ManyToManyField(OBElement)
    comprises = models.ManyToManyField('self', through='OBObjectComprisal')
    nested_objects = models.ManyToManyField('self', symmetrical=False)
    element_arrays = models.ManyToManyField('OBArrayOfElement')
    object_arrays = models.ManyToManyField('OBArrayOfObject')

    def __str__(self):
        return self.name


class OBObjectComprisal(models.Model):
    class Method(models.TextChoices):
        ALL_OF = 'allOf', _('allOf')
        ANY_OF = 'anyOf', _('anyOf')
        ONE_OF = 'oneOf', _('oneOf')
    target = models.ForeignKey(OBObject, on_delete=models.DO_NOTHING, related_name='obobjectcomposition_set')
    source = models.ForeignKey(OBObject, on_delete=models.DO_NOTHING)
    method = models.CharField(max_length=5, choices=Method, default=Method.ALL_OF)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['method', 'target'], name='unique_object_comprisal_strategy'),
        ]

    def __str__(self):
        return f'{self.target.name}<=={self.method}=={self.source.name}'


class OBArrayOfElement(models.Model):
    name = models.CharField(max_length=len('InverterEfficiencyCECTestResults'), unique=True)
    items = models.ForeignKey(OBElement, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.name


class OBArrayOfObject(models.Model):
    name = models.CharField(max_length=len('InverterEfficiencyCECTestResults'), unique=True)
    items = models.ForeignKey(OBObject, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.name
