"""
Script and tools for uploading Product data into the Product Registry.
It supports uploading the CEC Product data and expects the data to be Excel.

The script needs a predefined mapping between the columns in the data file and
the Orange Button taxonomy elements. Using the mapping, it transforms each row
of the data into a JSON instance of an Orange Button Product. The script
iterates over the JSON instance, and inserts rows into the database's tables
as needed.

For each new data file, there are six types of mappings or lists that can be
used to control how the data is uploaded:

    1. **COLUMN_DTYPES**: Tells pandas (the data file reader) what type to
       interpret each columns' data as. Usually pandas chooses the correct
       type; however decimal values should be read as strings, not floats.
       Later, when the data is uploaded to the database, these strings will be
       converted to Python Decimal types. These store decimal values more
       precisely than floats.
    1. **COLUMN_VALUE_TO_OB_VALUE**: Defines how to convert data values to
       Orange Button values. This can be used for Orange Button enumerations.
       It is a list of tuples of:

       .. code-block:: python

          ('<data_column_name>', ('<data_value>', <'OB_value'>))

       If a column does not have a corresponding Orange Button element, it can
       be skipped by mapping it to an empty tuple:

       .. code-block:: python

          ('<data_column_name>', tuple())

    1. **TO_OB_FIELD**: Defines the mapping from the columns of the data
       file to (a list of) the Orange Button elements and their primitives
       (Value, Unit, etc.). It is a dictionary of:

       .. code-block:: python

          {
              '<data_column_name>': (
                  # use the value from the data column
                  '<dot_path_to_element_in_Product>_<primitive>',
                  # use a defualt_value instead (useful for setting Unit)
                  ('<dot_path_to_element_in_Product>_<primitive>', <default_value>)
              )
          }

       The dot-paths can also handle nested arrays of Orange Button objects.
       Use ``<dot_path_to_array>.2`` to refer to the third object of the array.

    1. **EXTRA_DEFAULTS**: Extends **TO_OB_FIELD** to include known data for a
       Product that is not explicitly included in the data file. For example,
       for a file of ProdBattery data, we know the ProdType is ``Battery``. It
       is a dictionary of:

       .. code-block:: python

          {
              '<data_column_name>': (
                  ('<dot_path_to_element_in_Product>_<primitive>', <default_value>)
              )
          }

       Also, this is used to ensure rows for one-to-one related Orange Button
       objects are created. One-to-one related objects appear as nested JSON
       objects, and the database is designed to make one-to-one relationships
       required. For example, every Contact row must have an Address row even
       if there is no data for the Address when the Contact is created. To
       create a row that corresponds to a nested JSON object, add a dot-path
       to one of the Orange Button elements of that row with the appropriate
       default value. For example, to create a Dimension row to ProdBattery, we
       can set:

       .. code-block:: python

          EXTRA_DEFAULTS['ProdBattery.Dimension.Height_Value'] = None

    1. **ROW_SPECIFIC_TRANSFORMS**: Allows for doing for complicated data
       transforms on a row. For example, sometimes to store a list of values
       in Excel, a delimited list of values will be put in a cell. For Orange
       Button, these need to be split into a nested array, and splitting can
       be done through a row specific transform. This is a list of functions
       that will be run on each row of the data.
    1. **SUNSPEC_MFR_TO_CEC_MFR**: Used for creating Products' ProdCode.
       It maps SunSpec manufacturer names to CEC manufacturer names. Note
       the CEC sometimes uses multiple names for the same manufacturer. This
       is a list of tuples of:

       .. code-block:: python

          ('<SunSpec_mfr1_name>', '<CEC_mfr1_name1>'),
          ('<SunSpec_mfr1_name>', '<CEC_mfr1_name2>'),

After these are created, they can be passed to the :func:`upload` method to
begin uploading the data.
"""
from collections import OrderedDict
import datetime
from pathlib import Path
import re

from django.apps import apps
from django.db import models, transaction

import flatten_json  # to turn the dot-path notation into nested JSON objects
import pandas as pd  # easy IO for Excel and CSV files
import numpy as np
from tqdm import tqdm  # for upload progress and speed measurement


# where to put the data file
DATA_DIR = Path(__file__).parent / 'data'

# SunSpec manufacturer names Excel file
COMPANY_CODES_XLSX = DATA_DIR / 'COMPANY CODES.xlsx'
COMPANY_CODES = pd.read_excel(COMPANY_CODES_XLSX)

"""
CEC Battery to ProdBattery
"""

BATTERY_XLSX = DATA_DIR / 'Battery_List_Data_ADA.xlsx'

BATTERY_COLUMN_DTYPES = {
    'Nameplate Energy Capacity': str,
    'Maximum Continuous Discharge Rate2': str
}

BATTERY_COLUMN_VALUE_TO_OB_VALUE = (
    ('Edition of UL 1973', ('Ed. 2 : 2018', 'UL1973_2_2018')),
    ('Edition of UL 1973', ('Ed. 2: 2018', 'UL1973_2_2018')),
    ('Technology', ('Lithium Iron Phosphate', 'LiFePO4')),
    ('Technology', ('Lithium Iron Phospate', 'LiFePO4')),
    ('Technology', ('Lithium Iron\nPhosphate', 'LiFePO4')),
    ('Technology', ('Lithium-Ion', 'LiIon')),
    ('Technology', ('Lithium Ion', 'LiIon'))
)

BATTERY_TO_OB_FIELD = OrderedDict([
    ('Manufacturer Name', (
        'ProdBattery.ProdMfr_Value',
    )),
    ('Brand1', tuple()),
    ('Model Number', (
        'ProdBattery.ProdCode_Value',
    )),
    ('Technology', (
        'ProdBattery.BatteryChemistryType_Value',
    )),
    ('Description', (
        'ProdBattery.Description_Value',
    )),
    # Next three are under the super column UL 1973 Certification
    ('Certifying Entity', (
        'ProdBattery.ProdCertification.0.CertificationAgency.CertificationAgencyName_Value',
    )),
    ('Certification Date', (
        'ProdBattery.ProdCertification.0.CertificationDate_Value',
    )),
    ('Edition of UL 1973', (
        'ProdBattery.ProdCertification.0.CertificationStandard_Value',
    )),
    ('Nameplate Energy Capacity', (
        'ProdBattery.EnergyCapacityNominal_Value',
        ('ProdBattery.EnergyCapacityNominal_Unit', 'kWh')
    )),
    ('Maximum Continuous Discharge Rate2', (
        'ProdBattery.DCOutput.PowerDCContinuousMax_Value',
        ('ProdBattery.DCOutput.PowerDCContinuousMax_Unit', 'kW')
    )),
    ('Manufacturer Declared Roundtrip Efficiency', tuple()),
    ('Certified JA12 Control  Strategies1', tuple()),
    ('Declaration for JA12 Submitted1', tuple()),
    ('Notes', tuple()),
    ('CEC Listing Date', tuple()),
    ('Last Update', tuple()),
])

BATTERY_EXTRA_DEFAULTS = OrderedDict([
    ('ProdBattery.ProdType_Value', 'Battery'),
    ('ProdBattery.Dimension.Height_Value', None),
    ('ProdBattery.DCInput.MPPTNumber_Value', None)
])


BATTERY_SUNSPEC_MFR_TO_CEC_MFR = [
    ('Darfon Electronics Corporation', 'Darfon Electronics Corp.'),
    ('Fortress Power', 'Fortress Power LLC'),
    ('Holu Hou', 'Holu Hou Energy LLC'),
    ('LG Electronics Inc.', 'LG Energy Solution, Ltd.'),
    ('Simpliphi Power', 'SimpliPhi Power, Inc.'),
    ('SolarEdge Technologies Inc', 'SolarEdge Technologies Ltd.'),
]


def upload_cec_battery():
    dataframe = (
        pd.read_excel(BATTERY_XLSX, header=None, names=BATTERY_TO_OB_FIELD.keys(), dtype=BATTERY_COLUMN_DTYPES)[12:]
        .replace({np.nan: None})
        .drop_duplicates()
    )
    upload(
        model_name='ProdBattery',
        dataframe=dataframe,
        mfr_mapping=BATTERY_SUNSPEC_MFR_TO_CEC_MFR,
        field_mapping=BATTERY_TO_OB_FIELD,
        value_mapping=BATTERY_COLUMN_VALUE_TO_OB_VALUE,
        extra_default_fields=BATTERY_EXTRA_DEFAULTS,
        row_specific_transforms=tuple()
    )


MODULE_XLSX = DATA_DIR / 'PV_Module_List_Full_Data_ADA.xlsx'

MODULE_COLOMN_DTYPES = {
    'Model Number': str,
    'Nameplate Pmax': str,
    'PTC': str,
    'A_c': str,
    'Nameplate Isc': str,
    'Nameplate Voc': str,
    'Nameplate Ipmax': str,
    'Nameplate Vpmax': str,
    'Average NOCT': str,
    'γPmax': str,
    'αIsc': str,
    'βVoc': str,
    'αIpmax': str,
    'βVpmax': str,
    'IPmax, low': str,
    'VPmax, low': str,
    'IPmax, NOCT': str,
    'VPmax, NOCT': str,
    'Short Side': str,
    'Long Side': str
}

MODULE_COLOMN_VALUE_TO_OB_VALUE = (
    ('Description', (None, '')),
    ('Safety Certification', ('UL 1703', 'UL1703_2002')),
    ('Safety Certification', ('UL 1703 ', 'UL1703_2002')),
    ('Safety Certification', ('UL 1741', 'UL1741_2021')),
    ('Safety Certification', ('UL 61730', 'UL61730_2017')),
    ('Safety Certification', ('UL 61730 ', 'UL61730_2017')),
    ('Notes', (None, '')),
    ('Design Qualification Certification (Optional Submission)', ('No Information Submitted', None)),
    ('Performance Evaluation (Optional Submission)', ('No Information Submitted', None)),
    ('Technology', ('Mono-c-Si', 'MonoSi')),
    ('Technology', ('Multi-c-Si', 'PolySi')),
    ('Technology', ('Thin Film', 'ThinFilm')),
    ('Technology', ('CdTe', 'CdTe')),
    ('Technology', ('CIGS', 'CIGS')),
    ('BIPV', ('Y', True)),
    ('BIPV', ('N', False)),
    ('αIpmax', ('\xa0', None))
)

MODULE_TO_OB_FIELD = OrderedDict([
    ('Manufacturer Name', (  # Instead of Manufacturer as in the XLSX
        'ProdModule.ProdMfr_Value',
    )),
    ('Model Number', (
        'ProdModule.ProdCode_Value',
    )),
    ('Description', (
        'ProdModule.Description_Value',
    )),
    ('Safety Certification', (
        'ProdModule.ProdCertification.0.CertificationStandard_Value',
        ('ProdModule.ProdCertification.0.CertificationAgency.Description_Value', '')
    )),
    ('Nameplate Pmax', (
        'ProdModule.PowerSTC_Value',
        ('ProdModule.PowerSTC_Unit', 'W'),
        'ProdModule.ModuleElectRating.0.PowerDC_Value',
        ('ProdModule.ModuleElectRating.0.PowerDC_Unit', 'W'),
        ('ProdModule.ModuleElectRating.0.ModuleRatingCondition_Value', 'STC')
    )),
    ('PTC', (
        'ProdModule.ModuleElectRating.1.PowerDC_Value',
        ('ProdModule.ModuleElectRating.1.PowerDC_Unit', 'W'),
        ('ProdModule.ModuleElectRating.1.ModuleRatingCondition_Value', 'PTC')
    )),
    ('Notes', (
        'ProdModule.CECNotes_Value',
    )),
    ('Design Qualification Certification (Optional Submission)', (
        'ProdModule.ProdCertification.1.CertificationDate_Value',
        ('ProdModule.ProdCertification.1.CertificationStandard_Value', 'IEC61215_2016'),
        ('ProdModule.ProdCertification.1.CertificationAgency.Description_Value', '')
    )),
    ('Performance Evaluation (Optional Submission)', (
        'ProdModule.ProdCertification.2.CertificationDate_Value',
        ('ProdModule.ProdCertification.2.CertificationStandard_Value', 'IEC61853_1_2011'),
        ('ProdModule.ProdCertification.2.CertificationAgency.Description_Value', '')
    )),
    ('Family', tuple()),
    ('Technology', (
        'ProdModule.ProdCell.CellTechnologyType_Value',
    )),
    ('A_c', (
        'ProdModule.ModuleArea_Value',
        ('ProdModule.ModuleArea_Unit', 'sqm')
    )),
    ('N_s', (
        'ProdModule.CellsInSeries_Value',
    )),
    ('N_p', (
        'ProdModule.CellStringsParallelQuantity_Value',
    )),
    ('BIPV', (
        'ProdModule.IsBIPV_Value',
    )),

    ('Nameplate Isc', (
        'ProdModule.ModuleElectRating.2.CurrentShortCircuit_Value',
        ('ProdModule.ModuleElectRating.2.CurrentShortCircuit_Unit', 'A'),
    )),
    ('Nameplate Voc', (
        'ProdModule.ModuleElectRating.2.VoltageOpenCircuit_Value',
        ('ProdModule.ModuleElectRating.2.VoltageOpenCircuit_Unit', 'V'),
    )),
    ('Nameplate Ipmax', (
        'ProdModule.ModuleElectRating.2.CurrentAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.2.CurrentAtMaximumPower_Unit', 'A'),
    )),
    ('Nameplate Vpmax', (
        'ProdModule.ModuleElectRating.2.VoltageAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.2.VoltageAtMaximumPower_Unit', 'V'),
    )),

    ('Average NOCT', (
        'ProdModule.TemperatureNOCT_Value',
        ('ProdModule.TemperatureNOCT_Unit', 'Cel'),
    )),
    ('γPmax', (
        'ProdModule.TemperatureCoefficientMaximumPower_Value',
        ('ProdModule.TemperatureCoefficientMaximumPower_Unit', 'percent_per_Cel'),
    )),
    ('αIsc', (
        'ProdModule.TemperatureCoefficientShortCircuitCurrent_Value',
        ('ProdModule.TemperatureCoefficientShortCircuitCurrent_Unit', 'percent_per_Cel'),
    )),
    ('βVoc', (
        'ProdModule.TemperatureCoefficientOpenCircuitVoltage_Value',
        ('ProdModule.TemperatureCoefficientOpenCircuitVoltage_Unit', 'percent_per_Cel'),
    )),
    ('αIpmax', (
        'ProdModule.TemperatureCoefficientMaxPowerCurrent_Value',
        ('ProdModule.TemperatureCoefficientMaxPowerCurrent_Unit', 'percent_per_Cel'),
    )),
    ('βVpmax', (
        'ProdModule.TemperatureCoefficientMaxPowerVoltage_Value',
        ('ProdModule.TemperatureCoefficientMaxPowerVoltage_Unit', 'percent_per_Cel'),
    )),

    ('IPmax, low', (
        'ProdModule.ModuleElectRating.3.CurrentAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.3.CurrentAtMaximumPower_Unit', 'A'),

    )),
    ('VPmax, low', (
        'ProdModule.ModuleElectRating.3.VoltageAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.3.VoltageAtMaximumPower_Unit', 'V'),
    )),

    ('IPmax, NOCT', (
        'ProdModule.ModuleElectRating.4.CurrentAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.4.CurrentAtMaximumPower_Unit', 'A'),

    )),
    ('VPmax, NOCT', (
        'ProdModule.ModuleElectRating.4.VoltageAtMaximumPower_Value',
        ('ProdModule.ModuleElectRating.4.VoltageAtMaximumPower_Unit', 'V'),
    )),

    ('Mounting', tuple()),
    ('Type', tuple()),
    ('Short Side', (
        'ProdModule.Dimension.Width_Value',
        ('ProdModule.Dimension.Width_Unit', 'm'),
    )),
    ('Long Side', (
        'ProdModule.Dimension.Height_Value',
        ('ProdModule.Dimension.Length_Unit', 'm'),
    )),
    ('Geometric Multiplier', tuple()),
    ('P2/Pref', tuple()),
    ('CEC Listing Date', tuple()),
    ('Last Update', tuple())
])

MODULE_EXTRA_DEFAULTS = OrderedDict([
    ('ProdModule.ProdType_Value', 'Module'),
    ('ProdModule.IsCECListed_Value', True),
    ('ProdModule.ProdGlazing.Height_Value', None),
])


def SafetyCertificationDoubleUL(row):
    prefix = 'ProdModule.ProdCertification'
    saftey_cert = lambda i: f'{prefix}.{i}.CertificationStandard_Value'
    if row[saftey_cert(0)] == 'UL 61730, UL 1703':
        row[saftey_cert(0)] = 'UL1703_2002'
        next_idx = 1 + get_last_idx(row.keys(), prefix)
        row[saftey_cert(next_idx)] = 'UL61730_2017'
        required_1to1_field = f'{prefix}.{next_idx}.CertificationAgency.Description_Value'
        row[required_1to1_field] = ''


def DesignQualificationCertificationOptionalSubmission(row):
    prefix = 'ProdModule.ProdCertification.1'
    cert_date = f'{prefix}.CertificationDate_Value'
    if row[cert_date] == '4/4/2022 [IEC 61215:2021]':
        row[cert_date] = datetime.date(2022, 4, 4)
        cert_type = f'{prefix}.CertificationStandard_Value'
        row[cert_type] = 'IEC61215_2021'


def RemoveExtremelyLargeCellStringsParallelQuantity(row):
    key = 'ProdModule.CellStringsParallelQuantity_Value'
    if row[key] is not None and row[key] > 1e18:
        row[key] = None


MODULE_ROW_SPECIFIC_TRANSFORMS = (
    SafetyCertificationDoubleUL,
    DesignQualificationCertificationOptionalSubmission,
    RemoveExtremelyLargeCellStringsParallelQuantity,
)


MODULE_SUNSPEC_MFR_TO_CEC_MFR = [
    ('Caterpillar, Inc.', 'Caterpillar Inc.'),
    ('Enphase Energy', 'Enphase Energy Inc.'),
    ('Freedom Forever', 'Freedom Forever Procurement LLC'),
    ('General Electric Company', 'GE Energy'),
    ('Hanwha Q-Cells', 'Hanwha Q CELLS'),
    ('Hanwha Q-Cells', 'Hanwha Q CELLS (Qidong)'),
    ('Hanwha Q-Cells', 'Hanwha Q CELLS (Qidong) Co., Ltd.'),
    ('Hanwha Q-Cells', 'Hanwha SolarOne (Qidong)'),
    ('JinkoSolar Holding Co., Ltd.', 'Jinko Solar Co., Ltd.'),
    ('SunPower Corporation', 'SunPower'),
    ('SunPower Corporation', 'Sunpower'),
    ('Tesla', 'Tesla Inc.'),
]


def upload_cec_module():
    dataframe = (
        pd.read_excel(MODULE_XLSX, header=None, names=MODULE_TO_OB_FIELD.keys(), dtype=MODULE_COLOMN_DTYPES)[18:]
        .replace({np.nan: None})
        .drop_duplicates()
    )
    upload(
        model_name='ProdModule',
        dataframe=dataframe,
        mfr_mapping=MODULE_SUNSPEC_MFR_TO_CEC_MFR,
        field_mapping=MODULE_TO_OB_FIELD,
        value_mapping=MODULE_COLOMN_VALUE_TO_OB_VALUE,
        extra_default_fields=MODULE_EXTRA_DEFAULTS,
        row_specific_transforms=MODULE_ROW_SPECIFIC_TRANSFORMS
    )


def upload(model_name, dataframe, mfr_mapping, field_mapping, value_mapping,
           extra_default_fields, row_specific_transforms):
    data_cec = dataframe

    format_ProdCode_Value(data_cec, mfr_mapping)

    # COLUMN_VALUE_TO_OB_VALUE
    for col, (old_val, new_val) in value_mapping:
        convert_val(data_cec, col, old_val, new_val)

    # TO_OB_FIELD
    data_cec = [row.to_dict() for _, row in data_cec.iterrows()]
    data_ob = []
    for row in tqdm(data_cec, ascii=True, desc='field mapping'):
        row_ob = {}
        for src_name, mappings in field_mapping.items():
            assert isinstance(mappings, tuple), f'Mapping for "{src_name}" must be a tuple.'
            for m in mappings:
                match m:
                    case str():
                        row_ob[m] = row[src_name]
                    case [m, v]:
                        row_ob[m] = v
                    case _:
                        raise ValueError(f'Expected mapping for {src_name} to be tuple or str, but got {type(m)}')
        data_ob.append(row_ob)

    # EXTRA_DEFAULTS
    for row in tqdm(data_ob, ascii=True, desc='req 1to1 fields'):
        for ob_path, value in extra_default_fields.items():
            row[ob_path] = value

    # ROW_SPECIFIC_TRANSFORMS
    for row in tqdm(data_ob, ascii=True, desc='row specific transforms'):
        for t in row_specific_transforms:
            t(row)

    # convert dot-paths into Orange Button JSON
    data_ob = [flatten_json.unflatten_list(row, '.') for row in data_ob]

    # insert rows into database
    independent_and_1to1_models = OrderedDict()
    foreign_key_models = OrderedDict()
    for i, d in enumerate(tqdm(data_ob, ascii=True, desc='prep inserts')):
        build_model_kwarg_groups(model_name, d[model_name], independent_and_1to1_models, foreign_key_models)
    with transaction.atomic():
        product_internal_ids = save_model_kwarg_groups(independent_and_1to1_models, foreign_key_models)
    dataframe['internal_id'], dataframe['ProdID'] = zip(
        *django_model('Product').objects
        .filter(id__in=product_internal_ids)
        .values_list('id', 'ProdID_Value')
    )
    dataframe = dataframe.set_index('internal_id')
    insertions_filepath = DATA_DIR / f'upload-{model_name}-{datetime.datetime.now()}'
    dataframe.to_csv(insertions_filepath)
    print(f'Wrote insertion info to file! {insertions_filepath}')


def format_ProdCode_Value(df, mfr_mapping):
    # replace special characters with underscore
    prodcodes = df['Model Number'].map(lambda x: re.sub(r'[^0-9A-Za-z]', '_', x))
    cec_mfrs = df['Manufacturer Name'].str.strip()
    # prepend the company code and a hyphen
    # add the exact match company names to mfr_mapping
    for v in set(COMPANY_CODES['Name']).intersection(set(cec_mfrs)):
        mfr_mapping.append((v, v))
    for sunspec_mfr, cec_mfr in mfr_mapping:
        for row, _ in cec_mfrs[cec_mfrs == cec_mfr].items():
            prodcodes[row] = f"{COMPANY_CODES[COMPANY_CODES['Name'] == sunspec_mfr]['Company Code'].iloc[0]}-{prodcodes[row]}"
    # handle duplicates by appending a hyphen and a number
    duplicates = prodcodes[prodcodes.duplicated(keep=False)]
    for v in set(duplicates):
        for num, (row, _) in enumerate(duplicates[duplicates == v].items()):
            if '-' in v:
                # mfr has duplicate model numbers
                prodcodes[row] = f'{v}-{num+1}'
            else:
                # two or more mfrs have same model number, and the company code is unknown
                prodcodes[row] = f"{cec_mfrs[row]}-{v}"
    df['Model Number'] = prodcodes


def get_last_idx(keys, prefix):
    return max(int(re.search('[0-9]', k)[0]) for k in keys
               if k.startswith(prefix))


def django_model(model_name):
    return apps.get_model('server', model_name)


def build_model_kwarg_groups(model_name, d: dict, independent_and_1to1_models: OrderedDict, foreign_key_models: OrderedDict, from_fk_rel=False):
    fk_objs = {}
    kwargs = dict(_1to1_related=[])
    for k, v in d.items():
        if isinstance(v, list):
            fk_objs[k] = v
        elif isinstance(v, dict):
            kwargs['_1to1_related'].append((k, build_model_kwarg_groups(k, v, independent_and_1to1_models, foreign_key_models)))
        else:
            kwargs[k] = v
    if from_fk_rel:
        if model_name not in foreign_key_models:
            foreign_key_models[model_name] = OrderedDict()
        instance_id = f'{model_name}{len(foreign_key_models[model_name].keys())}'
        foreign_key_models[model_name][instance_id] = kwargs
    else:
        if model_name not in independent_and_1to1_models:
            independent_and_1to1_models[model_name] = OrderedDict()
        instance_id = f'{model_name}{len(independent_and_1to1_models[model_name].keys())}'
        independent_and_1to1_models[model_name][instance_id] = kwargs
    for k, v in fk_objs.items():
        for o in v:
            o['_1toM_related'] = model_name, instance_id, from_fk_rel
            build_model_kwarg_groups(k, o, independent_and_1to1_models, foreign_key_models, from_fk_rel=True)
    return instance_id


def save_model_kwarg_groups(independent_and_1to1_models: OrderedDict, foreign_key_models: OrderedDict):
    product_internal_ids = []

    def resolve_relations(info, has_1toM=False):
        for kwargs in info.values():
            for model_name_rel, instance_id_rel in kwargs.pop('_1to1_related'):
                kwargs[model_name_rel] = independent_and_1to1_models[model_name_rel][instance_id_rel]

            if has_1toM:
                model_name_rel, instance_id_rel, from_fk_rel = kwargs.pop('_1toM_related')
                fk_name = model_name_rel
                if hasattr(django_model(model_name), 'Product'):
                    fk_name = 'Product'
                saved = foreign_key_models if from_fk_rel else independent_and_1to1_models
                kwargs[fk_name] = saved[model_name_rel][instance_id_rel]

    def handle_insertions(model_name, info):
        d_model = django_model(model_name)
        current_ids = tuple(d_model.objects.values_list('id', flat=True))
        models_to_save = [d_model(**m) for m in info.values()]
        if is_multi_table_inheritance_model(d_model):
            multi_table_inheritance_bulk_create(models_to_save)
        else:
            d_model.objects.bulk_create(models_to_save)
        saved_models = d_model.objects.exclude(id__in=current_ids)
        for instance_id, model in zip(info.keys(), saved_models):
            info[instance_id] = model
            if hasattr(model, 'ProdID_Value'):
                product_internal_ids.append(model.id)

    for model_name, info in tqdm(independent_and_1to1_models.items(), ascii=True, desc='insert independent and 1to1'):
        resolve_relations(info)
        handle_insertions(model_name, info)

    for model_name, info in tqdm(foreign_key_models.items(), ascii=True, desc='insert 1toM'):
        resolve_relations(info, has_1toM=True)
        handle_insertions(model_name, info)

    return product_internal_ids


def multi_table_inheritance_bulk_create(models_to_save):
    if len(models_to_save) == 0:
        return
    model = models_to_save[0].__class__
    local_fields = model._meta.local_fields
    parent_model = model._meta.pk.related_model
    parent_fields = parent_model._meta.local_fields
    parent_current_ids = tuple(parent_model.objects.values_list('id', flat=True))
    parent_model.objects.bulk_create([
        parent_model(**{f.name: getattr(o, f.name) for f in parent_fields})
        for o in models_to_save
    ])
    parent_saved_models = parent_model.objects.exclude(id__in=parent_current_ids)
    for parent, o in zip(parent_saved_models, models_to_save):
        setattr(o, o._meta.pk.name, parent)
    qs = models.QuerySet(model)
    qs._for_write = True
    with transaction.atomic(savepoint=False):
        qs._batched_insert(models_to_save, local_fields, batch_size=None)


def is_multi_table_inheritance_model(model_class):
    # source: github.com/django/django/blob/main/db/models/query.py#L751
    return any(parent._meta.concrete_model is not model_class._meta.concrete_model for parent in model_class._meta.get_parent_list())


def convert_val(df, col, old_val, val):
    df[col] = df[col].replace(to_replace=[old_val], value=val)
    return df
