from collections import OrderedDict
import itertools

from django import forms
from django import template

from server import ob_item_types as obit, models


WIDGET_READONLY_ATTRS = {
    'readonly': 'true',
    'disabled': 'true',
    'class': 'form-control-plaintext',
    'style': '-webkit-appearance: none'  # hide the dropdown arrow of choice fields
}


@template.defaulttags.register.filter(name='dictkey')
def dictkey(d, k):
    return d[k]


@template.defaulttags.register.filter
def render_primitive_readonly(bound_field, primitive):
    subwidgets_dict = bound_field.field.widget.subwidgets_dict
    if primitive not in subwidgets_dict:
        return ''
    subwidget = bound_field.field.widget.subwidgets_dict[primitive]
    field_values = bound_field.value().copy()
    if subwidget.__class__ is forms.NumberInput and (v := field_values[primitive]) is not None:
        field_values[primitive] = round(v, 4)
    context = bound_field.field.widget.get_context(bound_field.html_name, field_values, attrs=WIDGET_READONLY_ATTRS)
    subwidget_context = context['widget']['subwidgets_dict'][primitive]
    return forms.boundfield.BoundWidget(subwidget, subwidget_context, bound_field.form.renderer)


class WidgetDate(forms.DateInput):
    template_name = 'server/forms/widgets/date.html'


class WidgetDateTime(forms.DateTimeInput):
    template_name = 'server/forms/widgets/datetime.html'


class WidgetOBElement(forms.MultiWidget):
    template_name = 'server/forms/widgets/multiwidget_obelement.html'

    def __init__(self, widgets: dict, attrs=None):
        self.subwidgets_dict = widgets
        super().__init__(widgets, attrs)

    def get_context(self, name, value, attrs):
        fname = name.split('-')[-1]
        values_list = []
        prims = set(p.name for p in obit.OBElement(fname).primitives())
        for wn in self.widgets_names:
            if (p := wn[1:]) in prims:
                values_list.append(value[p])
            else:
                values_list.append('')
        context = super().get_context(name, values_list, attrs)
        context['widget']['subwidgets_dict'] = {
            prim[1:]: sw_context
            for prim, sw_context in zip(self.widgets_names, context['widget']['subwidgets'])
        }
        return context

    def decompress(self, value):
        return [''] * 2

    def render(self, name, value, attrs=None, renderer=None):
        r = super().render(name, value, attrs=attrs, renderer=renderer)
        return r


class OBElement(forms.MultiValueField):
    def __init__(self, ob_element, **kwargs):  # required, label, initil, widget, help_text):
        self.ob_element = ob_element
        error_messages = dict(err='err')
        model_fields = ob_element.model_fields()
        fields = tuple(f.formfield() for f in model_fields.values())
        super().__init__(error_messages=error_messages, fields=fields, require_all_fields=False, **kwargs)

    def set_readonly(self, readonly: bool):
        field_widgets = OrderedDict()
        for p, f in zip(self.ob_element.primitives(), self.fields):
            if readonly:
                f.widget.attrs.update(WIDGET_READONLY_ATTRS)
            else:
                attrs = dict({'class': 'form-control'})
                match f:
                    case forms.DateTimeField():
                        f.widget = WidgetDateTime()
                    case forms.Field(choices=c):
                        if len(c) > 0:
                            attrs['class'] = 'form-select'
                f.widget.attrs.update(attrs)
            field_widgets[p.name] = f.widget
        self.widget = WidgetOBElement(field_widgets)

    def compress(self, data_list):
        pass


class FormMetaclass(forms.forms.DeclarativeFieldsMetaclass):
    def __new__(cls, name, bases, attrs):
        attrs['field_groups'] = attrs.get('field_groups', OrderedDict())
        if name != 'Form':
            match obit.get_schema_type(name):
                case obit.OBType.Element:
                    e = obit.OBElement(name, use_primitive_names=True)
                    for field_name, field in e.model_fields().items():
                        attrs[field_name] = field
                case _:
                    cls.add_ob_elements(name, attrs)
        return super().__new__(cls, name, bases, attrs)

    @classmethod
    def add_ob_elements(cls, name, attrs):
        elements = getattr(models, name).ob_elements
        for e in elements.values():
            attrs[e.name] = OBElement(e)


class Form(forms.Form, metaclass=FormMetaclass):
    def __init__(self, readonly=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.set_readonly(readonly)
        if not self.field_groups:
            self.field_groups[''] = tuple(sorted(self.fields))

    def get_initial_for_field(self, field, field_name):
        return self.initial[field_name]

    def fields_not_in_field_group(self):
        return tuple(
            e for e in obit.elements_of_ob_object(self.__class__.__name__)
            if e not in itertools.chain(*self.field_groups.values())
        )


class CertificationAgency(Form):
    pass


class DCInput(Form):
    pass


class DCOutput(Form):
    pass


class Dimension(Form):
    pass


class ModuleElectRating(Form):
    pass


class Product(Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_groups = OrderedDict([
            ('Product Information', (
                'ProdType',
                'ProdMfr',
                'ProdName',
                'Description',
                'ProdDatasheet',
                'FileFolderURL',
                'ProdCode',
                'ProdID'
            ))
        ])


class ProdBattery(Product):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_groups['Details'] = tuple(sorted(self.fields_not_in_field_group()))


class ProdCell(Form):
    pass


class ProdCertification(Form):
    pass


class ProdGlazing(Form):
    pass


class ProdModule(Product):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_groups['Certifications'] = (
            'IsCECListed',
            'CECListingDate',
            'CECNotes',
            'JunctionBoxProtectionCertification'
        )
        self.field_groups['Power/Product Warranties'] = (
            'PowerWarranty',
            'ProductWarranty'
        )
        self.field_groups['Details'] = tuple(sorted(self.fields_not_in_field_group()))
