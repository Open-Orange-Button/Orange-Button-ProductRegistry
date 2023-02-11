from django import forms

from server import ob_item_types as obit, models


class WidgetDate(forms.DateInput):
    template_name = 'server/forms/widgets/date.html'


class WidgetDateTime(forms.DateTimeInput):
    template_name = 'server/forms/widgets/datetime.html'


class WidgetOBElement(forms.MultiWidget):
    template_name = 'server/forms/widgets/multiwidget_obelement.html'

    def __init__(self, widgets, attrs=None):
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
        print(context)
        return context

    def decompress(self, value):
        return [''] * 2

    def render(self, name, value, attrs=None, renderer=None):
        r = super().render(name, value, attrs=attrs, renderer=renderer)
        print(r)
        return r


class OBElement(forms.MultiValueField):
    def __init__(self, ob_element, **kwargs):  # required, label, initil, widget, help_text):
        self.ob_element = ob_element
        error_messages = dict(err='err')
        model_fields = ob_element.model_fields()
        fields = tuple(f.formfield() for f in model_fields.values())
        super().__init__(error_messages=error_messages, fields=fields, require_all_fields=False, **kwargs)

    def set_readonly(self, readonly: bool):
        field_widgets = {}
        for p, f in zip(self.ob_element.primitives(), self.fields):
            if readonly:
                f.widget.attrs.update({
                    'readonly': 'true',
                    'disabled': 'true',
                    'class': 'form-control-plaintext'
                })
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

    def get_initial_for_field(self, field, field_name):
        return self.initial[field_name]


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
    pass


class ProdBattery(Product):
    pass


class ProdCell(Product):
    pass


class ProdCertification(Form):
    pass


class ProdGlazing(Form):
    pass


class ProdModule(Product):
    pass
