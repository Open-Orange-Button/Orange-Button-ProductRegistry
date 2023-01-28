from collections import OrderedDict
import datetime
from pathlib import Path
import re

from django.apps import apps
from django.db import models, transaction, utils
from django.core import exceptions

import flatten_json
import pandas as pd
import numpy as np
from tqdm import tqdm


DATA_DIR = Path(__file__).parent / 'data'

BATTERY_XLSX = DATA_DIR / 'Battery_List_Data_ADA.xlsx'

BATTERY_COLOMN_DTYPES = {
    'Nameplate Energy Capacity': str,
    'Maximum Continuous Discharge Rate2': str
}

BATTERY_COLOMN_VALUE_TO_OB_VALUE = (
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
        'ProdBattery.ProdCertification.0.CertificationTypeProduct_Value',
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


def upload_cec_battery():
    dataframe = pd.read_excel(BATTERY_XLSX, header=None, names=BATTERY_TO_OB_FIELD.keys(), dtype=BATTERY_COLOMN_DTYPES)[12:].replace({np.nan: None})
    upload(
        model_name='ProdBattery',
        dataframe=dataframe,
        field_mapping=BATTERY_TO_OB_FIELD,
        value_mapping=BATTERY_COLOMN_VALUE_TO_OB_VALUE,
        extra_default_fields=BATTERY_EXTRA_DEFAULTS,
        row_specific_transforms=tuple()
    )


MODULE_XLSX = DATA_DIR / 'PV_Module_List_Full_Data_ADA.xlsx'

MODULE_COLOMN_DTYPES = {
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
    ('Safety Certification', ('UL 1703', 'UL1703')),
    ('Safety Certification', ('UL 1703 ', 'UL1703')),
    ('Safety Certification', ('UL 1741', 'UL1741')),
    ('Safety Certification', ('UL 61730', 'UL61730')),
    ('Safety Certification', ('UL 61730 ', 'UL61730')),
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
    ('Manufacturer', (
        'ProdModule.ProdMfr_Value',
    )),
    ('Model Number', (
        'ProdModule.ProdCode_Value',
    )),
    ('Description', (
        'ProdModule.Description_Value',
    )),
    ('Safety Certification', (
        'ProdModule.ProdCertification.0.CertificationTypeProduct_Value',
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
        ('ProdModule.ProdCertification.1.CertificationTypeProduct_Value', 'IEC61215_2016'),
        ('ProdModule.ProdCertification.1.CertificationAgency.Description_Value', '')
    )),
    ('Performance Evaluation (Optional Submission)', (
        'ProdModule.ProdCertification.2.CertificationDate_Value',
        ('ProdModule.ProdCertification.2.CertificationTypeProduct_Value', 'IEC61853_1_2011'),
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
    ('ProdModule.ProdGlazing.Height_Value', None),
    ('ProdModule.ProdCell.Dimension.Height_Value', None)
])


def SafetyCertificationDoubleUL(row):
    prefix = 'ProdModule.ProdCertification'
    saftey_cert = lambda i: f'{prefix}.{i}.CertificationTypeProduct_Value'
    if row[saftey_cert(0)] == 'UL 61730, UL 1703':
        row[saftey_cert(0)] = 'UL1703'
        next_idx = 1 + get_last_idx(row.keys(), prefix)
        row[saftey_cert(next_idx)] = 'UL61730'
        required_1to1_field = f'{prefix}.{next_idx}.CertificationAgency.Description_Value'
        row[required_1to1_field] = ''


def DesignQualificationCertificationOptionalSubmission(row):
    prefix = 'ProdModule.ProdCertification.1'
    cert_date = f'{prefix}.CertificationDate_Value'
    if row[cert_date] == '4/4/2022 [IEC 61215:2021]':
        row[cert_date] = datetime.date(2022, 4, 4)
        cert_type = f'{prefix}.CertificationTypeProduct_Value'
        row[cert_type] = 'IEC61215_2021'


MODULE_ROW_SPECIFIC_TRANSFORMS = (
    SafetyCertificationDoubleUL,
    DesignQualificationCertificationOptionalSubmission
)


def upload_cec_module():
    dataframe = pd.read_excel(MODULE_XLSX, header=None, names=MODULE_TO_OB_FIELD.keys(), dtype=MODULE_COLOMN_DTYPES)[18:].replace({np.nan: None})
    upload(
        model_name='ProdModule',
        dataframe=dataframe,
        field_mapping=MODULE_TO_OB_FIELD,
        value_mapping=MODULE_COLOMN_VALUE_TO_OB_VALUE,
        extra_default_fields=MODULE_EXTRA_DEFAULTS,
        row_specific_transforms=MODULE_ROW_SPECIFIC_TRANSFORMS
    )


def upload(model_name, dataframe, field_mapping, value_mapping, extra_default_fields,
           row_specific_transforms):
    data_cec = dataframe
    for col, (old_val, new_val) in value_mapping:
        convert_val(data_cec, col, old_val, new_val)
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
    for row in tqdm(data_ob, ascii=True, desc='req 1to1 fields'):
        for ob_path, value in extra_default_fields.items():
            row[ob_path] = value
    for row in tqdm(data_ob, ascii=True, desc='row specific transforms'):
        for t in row_specific_transforms:
            t(row)
    data_ob = [flatten_json.unflatten_list(row, '.') for row in data_ob]
    with transaction.atomic():
        independent_and_1to1_models = OrderedDict()
        foreign_key_models = OrderedDict()
        for i, d in enumerate(tqdm(data_ob, ascii=True, desc='prep inserts')):
            build_model_kwarg_groups(model_name, d[model_name], independent_and_1to1_models, foreign_key_models)
        products = save_model_kwarg_groups(independent_and_1to1_models, foreign_key_models)
    prod_ids = []
    internal_ids = []
    for p in products:
        if not hasattr(p, 'prodcell'):
            prod_ids.append(getattr(p, 'ProdID_Value'))
            internal_ids.append(p.id)
    dataframe['ProdID'] = prod_ids
    dataframe['internal_id'] = internal_ids
    dataframe = dataframe.set_index('internal_id')
    insertions_filepath = DATA_DIR / f'upload-{model_name}-{datetime.datetime.now()}'
    dataframe.to_csv(insertions_filepath)
    print(f'Wrote insertion info to file! {insertions_filepath}')


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
    products = []

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
        models_to_save = []
        for kwargs in tqdm(info.values(), ascii=True, desc=f'constructing/validating models ({model_name})'):
            m = d_model(**kwargs)
            try:
                m.full_clean()
            except exceptions.ValidationError as e:
                import pdb
                pdb.set_trace()
                print(f'Validation error! {e}')
                raise e
            models_to_save.append(m)
        if is_multi_table_inheritance_model(d_model):
            saved_models = []
            for m in tqdm(models_to_save, ascii=True, desc=f'multi-table model ({model_name}): insert one by one'):
                m.save()
                saved_models.append(m)
        else:
            saved_models = d_model.objects.bulk_create(models_to_save)
        for instance_id, model in zip(info.keys(), saved_models):
            info[instance_id] = model
            if hasattr(model, 'ProdID_Value'):
                products.append(model)

    for model_name, info in tqdm(independent_and_1to1_models.items(), ascii=True, desc='insert independent and 1to1'):
        resolve_relations(info)
        handle_insertions(model_name, info)

    for model_name, info in tqdm(foreign_key_models.items(), ascii=True, desc='insert 1toM'):
        resolve_relations(info, has_1toM=True)
        handle_insertions(model_name, info)

    return products


def is_multi_table_inheritance_model(model_class):
    # source: github.com/django/django/blob/main/db/models/query.py#L751
    return any(parent._meta.concrete_model is not model_class._meta.concrete_model for parent in model_class._meta.get_parent_list())


def convert_val(df, col, old_val, val):
    df[col] = df[col].replace(to_replace=[old_val], value=val)
    return df
