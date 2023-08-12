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
from collections import OrderedDict, defaultdict
import datetime
from pathlib import Path
import re

from django.apps import apps
from django.db import models, transaction

import flatten_json  # to turn the dot-path notation into nested JSON objects
import numpy as np
import pandas as pd  # easy IO for Excel and CSV files
from tqdm import tqdm  # for upload progress and speed measurement


DROP_COL_PREFIX = 'DROP_'


# where to put the data file
DATA_DIR = Path(__file__).parent / 'data'

# SunSpec manufacturer names Excel file
COMPANY_CODES_XLSX = DATA_DIR / 'COMPANY CODES.xlsx'

"""
CEC Battery to ProdBattery
"""

BATTERY_XLSX = DATA_DIR / 'Battery_List_Data_ADA.xlsx'

MODULE_XLSX = DATA_DIR / 'PV_Module_List_Full_Data_ADA.xlsx'


class ConverterEnums:
    def __init__(self, col, values_map):
        self.col = col
        self.values_map = values_map

    def __call__(self, df):
        if len(unknown := set(df[self.col].unique()) - set(self.values_map)) > 0:
            raise ValueError(f'Column values missing from conversion mapping: {"|".join(map(repr, unknown))}')
        for k, v in self.values_map.items():
            df[self.col][df[self.col] == k] = v
        return df


class ConverterEnumsMultivalue:
    def __init__(self, col_fn, col_idx, values_map, multiple_value_columns):
        self.col_fn = col_fn
        self.col_idx = col_idx
        self.values_map = values_map
        self.multiple_value_columns = multiple_value_columns

    def __call__(self, df):
        if len(unknown := set(df[self.col].unique()) - set(self.values_map)) > 0:
            raise ValueError(f'Column values missing from conversion mapping: {"|".join(map(repr, unknown))}')
        base_col = self.col_fn(self.col_idx)
        for k, v in self.values_map.items():
            if isinstance(v, list):
                products = (df[base_col] == k).index
                idxs = self.col_idx + np.arange(len(v))
                for p in products:
                    self.multiple_value_columns[p].update({
                        col: vv
                        for col, vv in zip(map(self.col_fn, idxs), v)
                    })
            else:
                df[base_col][df[base_col] == k] = v
        return df


class ConverterDType:
    def __init__(self, col, conversion_func):
        self.col = col
        self.conversion_func = conversion_func

    def __call__(self, df):
        df[self.col] = self.conversion_func(df[self.col])
        return df


class CECDataExcel:
    def __init__(self, file_path):
        self.multiple_value_columns = defaultdict(dict)
        self.company_codes = pd.read_excel(COMPANY_CODES_XLSX, dtype_backend='pyarrow')
        self.converters = []
        self.fixed_value_columns = {}
        self.value_copy_columns = {}
        self.file_path = file_path
        self.df = self.load_file()

    @property
    def ob_product(self):
        raise NotImplementedError

    def load_file(self):
        raise NotImplementedError

    def convert_column_values(self):
        for c in self.converters:
            self.df = c(self.df)

    def add_fixed_value_columns(self):
        for c, v in self.fixed_value_columns.items():
            self.df[c] = v

    def add_value_copy_columns(self):
        for c1, c2 in self.value_copy_columns.items():
            self.df[c1] = self.df[c2]

    def set_prodcodes(self):
        col_prodcode = f'{self.ob_product}.ProdCode_Value'
        for mfr, cc in zip(self.company_codes['Name'], self.company_codes['Company Code']):
            idx_products = self.df[f'{self.ob_product}.ProdMfr_Value'] == mfr
            products = self.df[idx_products]
            if products.size == 0:
                continue
            # replace special characters
            model_names = products[col_prodcode].str.replace(r'[^0-9A-Za-z]', '_', regex=True)
            self.df.loc[idx_products, col_prodcode] = cc + '-' + model_names

        # handle duplicates by appending a hyphen and a number
        # FIXME: does not account for data existing in database
        dupes_mask = self.df[col_prodcode].duplicated(keep=False)
        if dupes_mask.any():
            self.df.loc[dupes_mask, col_prodcode] += '-' + (
                self.df.groupby(col_prodcode).cumcount().add(1).astype(str)
            )

    def process(self):
        self.convert_column_values()
        self.add_fixed_value_columns()
        self.set_prodcodes()

    def to_json(self):
        return [flatten_json.unflatten_list(row, '.') for row in self.df.to_dict('records')]


class CECDataExcelBattery(CECDataExcel):
    def __init__(self, file_path):
        super().__init__(file_path)
        self.colnames = [
            'ProdBattery.ProdMfr_Value',  # Manufacturer Name
            f'{DROP_COL_PREFIX}Brand1',  # Brand1
            'ProdBattery.ProdCode_Value',  # Model Number
            'ProdBattery.BatteryChemistryType_Value',  # Technology
            'ProdBattery.Description_Value',  # Descrition
            # Next three are under the super column UL 1973 Certification
            'ProdBattery.ProdCertification.0.CertificationAgency.CertificationAgencyName_Value',  # Certifying Entity
            'ProdBattery.ProdCertification.0.CertificationDate_Value',  # Certification Date
            'ProdBattery.ProdCertification.0.CertificationStandard_Value',  # Edition of UL 1973
            'ProdBattery.EnergyCapacityNominal_Value',  # Nameplate Energy Capacity
            'ProdBattery.DCOutput.PowerDCContinuousMax_Value',  # Maximum Continuous Discharge Rate2
            f'{DROP_COL_PREFIX}Manufacturer Declared Roundtrip Efficiency',  # Manufacturer Declared Roundtrip Efficiency
            f'{DROP_COL_PREFIX}Certified JA12 Control  Strategies1',  # Certified JA12 Control  Strategies1
            f'{DROP_COL_PREFIX}Declaration for JA12 Submitted1',  # Declaration for JA12 Submitted1
            f'{DROP_COL_PREFIX}Notes',  # Notes
            f'{DROP_COL_PREFIX}CEC Listing Date',  # CEC Listing Date
            f'{DROP_COL_PREFIX}Last Update',  # Last Update
        ]
        self.fixed_value_columns = {
            'ProdBattery.EnergyCapacityNominal_Unit': 'kWh',
            'ProdBattery.DCOutput.PowerDCContinuousMax_Unit': 'kW',
            'ProdBattery.ProdType_Value': 'Battery',
            'ProdBattery.Dimension.Height_Value': None,
            'ProdBattery.DCInput.MPPTNumber_Value': None,
        }
        self.converters = [
            ConverterEnums(
                'ProdBattery.ProdCertification.0.CertificationStandard_Value',
                {'Ed. 2 : 2018': 'UL1973_2_2018',
                 'Ed. 3 : 2022': 'UL1973_2_2018'}
            ),
            ConverterEnums(
                'ProdBattery.BatteryChemistryType_Value',
                {'Lithium Iron': 'LiFePO4',
                 'Lithium iron phosphate': 'LiFePO4',
                 'Lithium Iron Phosphate': 'LiFePO4',
                 'Lithium-Ion': 'LiIon'}
            ),
            # ConverterEnums(
                # 'ProdBattery.ProdMfr_Value',
                # {n: c for n, c in zip(company_codes['Name'], company_codes['Company Code'])}
            # )
            ConverterDType('ProdBattery.ProdCertification.0.CertificationDate_Value', pd.to_datetime),
        ]

    @property
    def ob_product(self):
        return 'ProdBattery'

    def load_file(self):
        df = pd.read_excel(
            self.file_path,
            header=None,
            names=self.colnames,
            dtype='string[pyarrow]',
            skiprows=12,
            dtype_backend='pyarrow'
        ).drop_duplicates()
        return df[(c for c in df.columns if not c.startswith(DROP_COL_PREFIX))]


class CECDataExcelModule(CECDataExcel):
    def __init__(self, file_path):
        super().__init__(file_path)
        self.colnames = [
            'ProdModule.ProdMfr_Value',  # Manufacturer Name
            'ProdModule.ProdCode_Value',  # Model Number
            'ProdModule.Description_Value',  # Description
            'ProdModule.ProdCertification.0.CertificationStandard_Value',  # Safety Certification
            'ProdModule.ModuleElectRating.0.PowerDC_Value',  # Nameplate Pmax
            'ProdModule.ModuleElectRating.1.PowerDC_Value',  # PTC
            'ProdModule.CECNotes_Value',  # Notes
            'ProdModule.ProdCertification.1.CertificationDate_Value',  # Design Qualification Certification (Optional Submission)
            'ProdModule.ProdCertification.2.CertificationDate_Value',  # Performance Evaluation (Optional Submission)
            f'{DROP_COL_PREFIX}Family',  # Family
            'ProdModule.ProdCell.CellTechnologyType_Value',  # Technology
            'ProdModule.ModuleArea_Value',  # A_c
            'ProdModule.CellsInSeries_Value',  # N_s
            'ProdModule.CellStringsParallelQuantity_Value',  # N_p
            'ProdModule.IsBIPV_Value',  # BIPV
            'ProdModule.ModuleElectRating.2.CurrentShortCircuit_Value',  # Nameplate Isc
            'ProdModule.ModuleElectRating.2.VoltageOpenCircuit_Value',  # Nameplate Voc
            'ProdModule.ModuleElectRating.2.CurrentAtMaximumPower_Value',  # Nameplate Ipmax
            'ProdModule.ModuleElectRating.2.VoltageAtMaximumPower_Value',  # Nameplate Vpmax
            'ProdModule.TemperatureNOCT_Value',  # Average NOCT
            'ProdModule.TemperatureCoefficientMaximumPower_Value',  # γPmax
            'ProdModule.TemperatureCoefficientShortCircuitCurrent_Value',  # αIsc
            'ProdModule.TemperatureCoefficientOpenCircuitVoltage_Value',  # βVoc
            'ProdModule.TemperatureCoefficientMaxPowerCurrent_Value',  # αIpmax
            'ProdModule.TemperatureCoefficientMaxPowerVoltage_Value',  # βVpmax
            'ProdModule.ModuleElectRating.3.CurrentAtMaximumPower_Value',  # IPmax, low
            'ProdModule.ModuleElectRating.3.VoltageAtMaximumPower_Value',  # VPmax, low
            'ProdModule.ModuleElectRating.4.CurrentAtMaximumPower_Value',  # IPmax, NOCT
            'ProdModule.ModuleElectRating.4.VoltageAtMaximumPower_Value',  # VPmax, NOCT
            f'{DROP_COL_PREFIX}Mounting',  # Mounting
            f'{DROP_COL_PREFIX}Type',  # Type
            'ProdModule.Dimension.Width_Value',  # Short Side
            'ProdModule.Dimension.Height_Value',  # Long Side
            f'{DROP_COL_PREFIX}Geometric Multiplier',  # Geometric Multiplier
            f'{DROP_COL_PREFIX}P2/Pref',  # P2/Pref
            f'{DROP_COL_PREFIX}CEC Listing Date',  # CEC Listing Date
            f'{DROP_COL_PREFIX}Last Update',  # Last Update
        ]
        self.fixed_value_columns = {
            'ProdModule.ProdType_Value': 'Module',
            'ProdModule.IsCECListed_Value': True,
            'ProdModule.ProdGlazing.Height_Value': None,
            'ProdModule.ProdCertification.0.CertificationAgency.Description_Value': '',
            'ProdModule.PowerSTC_Unit': 'W',
            'ProdModule.ModuleElectRating.0.PowerDC_Unit': 'W',
            'ProdModule.ModuleElectRating.0.ModuleRatingCondition_Value': 'STC',
            'ProdModule.ModuleElectRating.1.PowerDC_Unit': 'W',
            'ProdModule.ModuleElectRating.1.ModuleRatingCondition_Value': 'PTC',
            'ProdModule.ModuleElectRating.2.CurrentShortCircuit_Unit': 'A',
            'ProdModule.ModuleElectRating.2.VoltageOpenCircuit_Unit': 'V',
            'ProdModule.ModuleElectRating.2.CurrentAtMaximumPower_Unit': 'A',
            'ProdModule.ModuleElectRating.2.VoltageAtMaximumPower_Unit': 'V',
            'ProdModule.ModuleElectRating.3.CurrentAtMaximumPower_Unit': 'A',
            'ProdModule.ModuleElectRating.3.VoltageAtMaximumPower_Unit': 'V',
            'ProdModule.ModuleElectRating.4.CurrentAtMaximumPower_Unit': 'A',
            'ProdModule.ModuleElectRating.4.VoltageAtMaximumPower_Unit': 'V',
            'ProdModule.ProdCertification.1.CertificationStandard_Value': 'IEC61215_2016',
            'ProdModule.ProdCertification.1.CertificationAgency.Description_Value': '',
            'ProdModule.ProdCertification.2.CertificationStandard_Value': 'IEC61853_1_2011',
            'ProdModule.ProdCertification.2.CertificationAgency.Description_Value': '',
            'ProdModule.ModuleArea_Unit': 'sqm',
            'ProdModule.TemperatureNOCT_Unit': 'Cel',
            'ProdModule.TemperatureCoefficientMaximumPower_Unit': 'percent_per_Cel',
            'ProdModule.TemperatureCoefficientShortCircuitCurrent_Unit': 'percent_per_Cel',
            'ProdModule.TemperatureCoefficientOpenCircuitVoltage_Unit': 'percent_per_Cel',
            'ProdModule.TemperatureCoefficientMaxPowerCurrent_Unit': 'percent_per_Cel',
            'ProdModule.TemperatureCoefficientMaxPowerVoltage_Unit': 'percent_per_Cel',
            'ProdModule.Dimension.Width_Unit': 'm',
            'ProdModule.Dimension.Length_Unit': 'm',
        }
        self.value_copy_columns = {
            'ProdModule.ModuleElectRating.0.PowerDC_Value': 'ProdModule.PowerSTC_Value',
        }
        self.converters = [
            ConverterEnumsMultivalue(
                lambda i: f'ProdModule.ProdCertification.{i}.CertificationStandard_Value',
                0,
                {'UL 1703': 'UL1703_2002',
                 'UL 1703 ': 'UL1703_2002',
                 'UL 1741': 'UL1741_2021',
                 'UL 61730 ': 'UL61730_2017',
                 'UL61730 ': 'UL61730_2017',
                 'UL61731 ': 'UL61730_2017',
                 'UL 61730, UL 1703': ['UL61730_2017', 'UL1703_2002']},
                self.multiple_value_column
            ),
            ConverterEnums(
                'ProdModule.ProdCertification.1.CertificationDate_Value',
                {'No Information Submitted', None}
            ),
            ConverterEnums(
                'ProdModule.ProdCertification.2.CertificationDate_Value',
                {'No Information Submitted', None}
            ),
            ConverterEnums(
                'ProdModule.ProdCell.CellTechnologyType_Value',
                {'Mono-c-Si': 'MonoSi',
                 'Multi-c-Si': 'PolySi',
                 'Thin Film': 'ThinFilm',
                 'CdTe': 'CdTe',
                 'CIGS': 'CIGS'}
            ),
            ConverterEnums(
                'ProdModule.IsBIPV_Value',
                {'Y': True, 'N': False}
            ),
            ConverterEnums(
                'ProdModule.TemperatureCoefficientMaxPowerCurrent_Value',
                {'\xa0': None}
            ),
            # ConverterEnums(
                # 'ProdBattery.ProdMfr_Value',
                # {n: c for n, c in zip(company_codes['Name'], company_codes['Company Code'])}
            # )
            ConverterDType('ProdModule.ProdCertification.1.CertificationDate_Value', pd.to_datetime),
            ConverterDType('ProdModule.ProdCertification.2.CertificationDate_Value', pd.to_datetime),
        ]

    @property
    def ob_product(self):
        return 'ProdModule'

    def load_file(self):
        df = pd.DataFrame(pd.read_excel(
            self.file_path,
            header=None,
            names=self.colnames,
            dtype=str,
            skiprows=18,
        ).to_dict('series'), dtype='string[pyarrow]').drop_duplicates()
        return df[(c for c in df.columns if not c.startswith(DROP_COL_PREFIX))]


def upload_cec_battery():
    data = CECDataExcelBattery(BATTERY_XLSX)
    data.process()
    upload(data)


def upload_cec_module():
    data = CECDataExcelModule(MODULE_XLSX)
    data.process()
    upload(data)


def upload(data):
    df = data.df
    records = data.to_json()
    model_name = data.ob_product
    # insert rows into database
    independent_and_1to1_models = OrderedDict()
    foreign_key_models = OrderedDict()
    for i, d in enumerate(tqdm(records, ascii=True, desc='prep inserts')):
        build_model_kwarg_groups(model_name, d[model_name], independent_and_1to1_models, foreign_key_models)
    with transaction.atomic():
        product_internal_ids = save_model_kwarg_groups(independent_and_1to1_models, foreign_key_models)
    df['internal_id'], df['ProdID'] = zip(
        *django_model('Product').objects
        .filter(id__in=product_internal_ids)
        .values_list('id', 'ProdID_Value')
    )
    df = df.set_index('internal_id')
    insertions_filepath = DATA_DIR / f'upload-{model_name}-{datetime.datetime.now()}'
    df.to_csv(insertions_filepath)
    print(f'Wrote insertion info to file! {insertions_filepath}')


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
