from collections import OrderedDict

import pytest

from server import serializers, models


@pytest.fixture
def Dimension():
    return models.Dimension.objects.create()


@pytest.fixture
def Product(Dimension):
    return models.Product.objects.create(Dimension=Dimension)


@pytest.fixture
def ProdMeter(Dimension):
    return models.ProdMeter.objects.create(Dimension=Dimension)


@pytest.fixture
def ProdSpecification(Product):
    return models.ProdSpecification.objects.create(Product=Product)


@pytest.fixture
def ProdSpecificationOfProdMeter(ProdMeter):
    return models.ProdSpecification.objects.create(Product=ProdMeter)


def test_wrap_with_id_and_unflatten():
    input = [
        {'id': 1, 'object1': 'a'},
        {'id': 1, 'object1_object2': 'b'}
    ]
    output = OrderedDict([(1, {'id': 1, 'object1': {'object2': 'b'}})])

    assert output == serializers.wrap_with_id_and_unflatten(input)


@pytest.mark.django_db
def test_get_values_by_ids(Product):
    product_ids = [Product.id]

    assert set(product_ids) == set(serializers.get_values_by_ids('Product', product_ids).keys())


@pytest.mark.django_db
def test_get_values_by_ids_fields_include(Product):
    product_ids = [Product.id]

    values = serializers.get_values_by_ids('Product', product_ids, fields_include={'id': ''})
    value = list(values.values())[0]

    assert {'id'} == set(value.keys())


@pytest.mark.django_db
def test_get_values_by_fk_ids(ProdSpecification):
    fk_ids = [ProdSpecification.Product.id]

    assert {ProdSpecification.id} == set(serializers.get_values_by_fk_ids('ProdSpecification', 'Product', fk_ids))


@pytest.mark.django_db
def test_get_values_by_fk_ids_fields_include(ProdSpecification):
    fk_ids = [ProdSpecification.Product.id]

    values = serializers.get_values_by_fk_ids('ProdSpecification', 'Product', fk_ids, fields_include={'id': ''})
    value = list(values.values())[0]

    assert {'id'} == set(value.keys())


def primitives_number():
    return dict(Decimals=None, EndTime=None, Precision=None, StartTime=None, Unit='', Value=None)


def primitives_string():
    return dict(EndTime=None, StartTime=None, Value='')


def primitives_date():
    return dict(EndTime=None, StartTime=None, Value=None)


def expected_serialized_Dimension():
    return dict((f, primitives_number()) for f in ('Height', 'Length', 'Mass', 'Weight', 'Width'))


def expected_serialized_ProdSpecification(product):
    res = dict((f, primitives_string()) for f in ('Description', 'SpecificationName', 'SpecificationType', 'SpecificationUnit', 'SpecificationValue'))
    res['Product'] = dict(id=product.id)
    return res


def expected_serialized_Product(product):
    ProdSpecification_serialized = expected_serialized_ProdSpecification(product)
    del ProdSpecification_serialized['Product']
    ProdID_serialized = primitives_string()
    ProdID_serialized['Value'] = product.ProdID_Value
    return dict(
        Description=primitives_string(), FileFolderURL=primitives_string(),
        ProdCode=primitives_string(), ProdDatasheet=primitives_string(),
        ProdID=ProdID_serialized, ProdMfr=primitives_string(),
        ProdName=primitives_string(), ProdType=primitives_string(),
        Dimension=expected_serialized_Dimension(), ProdInstructions=[],
        ProdSpecifications=[ProdSpecification_serialized],
        ProdCertifications=[], Packages=[], Warranties=[],
        AlternativeIdentifiers=[], SubstituteProducts=[]
    )


def expected_serialized_ProdMeter(product):
    res = expected_serialized_Product(product)
    res.update(dict(
        AccuracyClassANSI=primitives_number(),
        CECListingDate=primitives_date(),
        CECNotes=primitives_string(),
        DisplayDescription=primitives_string()
    ))
    return res


@pytest.mark.django_db
def test_serialize_by_ids_Dimension(Dimension):
    assert {Dimension.id: expected_serialized_Dimension()} == serializers.serialize_by_ids('Dimension', [Dimension.id])


@pytest.mark.django_db
def test_serialize_by_ids_ProdSpecifications(ProdSpecification):
    assert {ProdSpecification.id: expected_serialized_ProdSpecification(ProdSpecification.Product)} == serializers.serialize_by_ids('ProdSpecification', [ProdSpecification.id])


@pytest.mark.django_db
def test_serialize_Products(ProdSpecification):
    product = ProdSpecification.Product

    assert {product.id: expected_serialized_Product(product)} == serializers.serialize_Products('Product', [product.id])


@pytest.mark.django_db
def test_serialize_Products_Inheritance(ProdSpecificationOfProdMeter):
    product = ProdSpecificationOfProdMeter.Product

    assert {product.id: expected_serialized_ProdMeter(product)} == serializers.serialize_Products('ProdMeter', [product.id])
