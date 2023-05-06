import json

import pytest

from server import ob_item_types as obit


@pytest.fixture
def ob_taxonomy():
    with open(obit.OB_TAXONOMY_FILEPATH) as f:
        return json.load(f)


@pytest.mark.parametrize('name', [
    'BooleanItemType',
    'InverterItemType',
    'AreaItemType'
])
def test_item_type_from_name(name, ob_taxonomy):
    item_type_json = ob_taxonomy['x-ob-item-types'][name]
    item_type = obit.item_type_from_name(name)

    assert item_type.name is obit.ItemTypeName(name)
    assert item_type.description == item_type_json['description']

    if 'enums' in item_type_json:
        assert len(item_type.values) == len(item_type_json['enums'])
    elif 'units' in item_type_json:
        assert len(item_type.values) == len(item_type_json['units'])


def test_get_ref_schema():
    assert obit.get_ref_schema('#/unknown/path/to/object') == 'object'


@pytest.mark.parametrize('name, ob_type', [
    ('Value', obit.OBType.Primitive),
    ('AHJName', obit.OBType.Element),
    ('TaxonomyElementString', obit.OBType.Object),
    ('Contact', obit.OBType.Object),
    ('Signatory', obit.OBType.Object),
    ('Contacts', obit.OBType.Array)
])
def test_get_schema_type(name, ob_type):
    assert obit.get_schema_type(name) is ob_type


def test_ob_object_properties(ob_taxonomy):
    assert set(obit.ob_object_properties('Contact')) == set(ob_taxonomy['components']['schemas']['Contact']['properties'])

    # inheritance
    assert set(obit.ob_object_properties('Signatory')) == set(ob_taxonomy['components']['schemas']['Signatory']['allOf'][1]['properties'])


def test_ob_object_usage_as_array():
    assert 'ACInput' in obit.ob_object_usage_as_array('FrequencyAC', ['ACInput'])
