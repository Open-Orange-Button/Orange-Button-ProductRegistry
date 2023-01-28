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
        to_save = OrderedDict()
        to_save_fk = OrderedDict()
        for i, d in enumerate(tqdm(data_ob, ascii=True, desc='prep inserts')):
            build_models_to_save(model_name, d[model_name], to_save, to_save_fk)
        products = save_model_builds(to_save, to_save_fk)
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


def save_model_from_dict(model_name: str, d: dict):
    fk_objs = {}
    kwargs = {}
    for k, v in d.items():
        if isinstance(v, list):
            fk_objs[k] = v
        elif isinstance(v, dict):
            kwargs[k] = save_model_from_dict(k, v)
        else:
            kwargs[k] = v
    try:
        new_model = django_model(model_name)(**kwargs)
        new_model.full_clean()
        new_model.save()
    except (TypeError, utils.IntegrityError, exceptions.ValidationError) as e:
        print(e)
        import pdb
        pdb.set_trace()
        print('A validation error occured!')
        raise e
    for k, v in fk_objs.items():
        fk_name = model_name
        if hasattr(django_model(k), 'Product'):
            fk_name = 'Product'
        for m in v:
            m[fk_name] = new_model
            save_model_from_dict(k, m)
    return new_model


def build_models_to_save(model_name, d: dict, to_save: OrderedDict, to_save_fk: OrderedDict, from_fk_rel=False):
    fk_objs = {}
    kwargs = dict(_1to1_related=[])
    for k, v in d.items():
        if isinstance(v, list):
            fk_objs[k] = v
        elif isinstance(v, dict):
            kwargs['_1to1_related'].append((k, build_models_to_save(k, v, to_save, to_save_fk)))
        else:
            kwargs[k] = v
    if from_fk_rel:
        if model_name not in to_save_fk:
            to_save_fk[model_name] = OrderedDict()
        instance_id = f'{model_name}{len(to_save_fk[model_name].keys())}'
        to_save_fk[model_name][instance_id] = kwargs
    else:
        if model_name not in to_save:
            to_save[model_name] = OrderedDict()
        instance_id = f'{model_name}{len(to_save[model_name].keys())}'
        to_save[model_name][instance_id] = kwargs
    for k, v in fk_objs.items():
        for o in v:
            o['_1toM_related'] = model_name, instance_id, from_fk_rel
            build_models_to_save(k, o, to_save, to_save_fk, from_fk_rel=True)
    return instance_id


def save_model_builds(to_save: OrderedDict, to_save_fk: OrderedDict):
    products = []
    for model_name, info in tqdm(to_save.items(), ascii=True, desc='insert independent and 1to1'):
        for kwargs in info.values():
            for model_name_rel, instance_id_rel in kwargs.pop('_1to1_related'):
                kwargs[model_name_rel] = to_save[model_name_rel][instance_id_rel]
        d_model = django_model(model_name)
        models_to_save = [d_model(**m) for m in info.values()]
        if is_multi_table_inheritance_model(d_model):
            saved_models = []
            for m in tqdm(models_to_save, ascii=True, desc=f'multi-table model {model_name}: insert one by one'):
                m.save()
                saved_models.append(m)
        else:
            saved_models = d_model.objects.bulk_create(models_to_save)
        for instance_id, model in zip(info.keys(), saved_models):
            info[instance_id] = model
            if hasattr(model, 'ProdID_Value'):
                products.append(model)
    for model_name, info in tqdm(to_save_fk.items(), ascii=True, desc='insert 1toM'):
        for kwargs in info.values():
            model_name_rel, instance_id_rel, from_fk_rel = kwargs.pop('_1toM_related')
            fk_name = model_name_rel
            if hasattr(django_model(model_name), 'Product'):
                fk_name = 'Product'
            saved = to_save_fk if from_fk_rel else to_save
            kwargs[fk_name] = saved[model_name_rel][instance_id_rel]
            for model_name_rel, instance_id_rel in kwargs.pop('_1to1_related'):
                kwargs[model_name_rel] = to_save[model_name_rel][instance_id_rel]
        d_model = django_model(model_name)
        models_to_save = [d_model(**m) for m in info.values()]
        if is_multi_table_inheritance_model(d_model):
            saved_models = []
            for m in tqdm(models_to_save, ascii=True, desc=f'multi-table model {model_name}: insert one by one'):
                m.save()
                saved_models.append(m)
        else:
            saved_models = d_model.objects.bulk_create(models_to_save)
        for instance_id, model in zip(info.keys(), saved_models):
            info[instance_id] = model
            if hasattr(model, 'ProdID_Value'):
                products.append(model)
    return products


def is_multi_table_inheritance_model(model_class):
    # source: github.com/django/django/blob/main/db/models/query.py#L751
    return any(parent._meta.concrete_model is not model_class._meta.concrete_model for parent in model_class._meta.get_parent_list())


def convert_val(df, col, old_val, val):
    df[col] = df[col].replace(to_replace=[old_val], value=val)
    return df
