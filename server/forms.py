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
        field_widgets = {}
        for k, f in zip(model_fields, fields):
            attrs = dict({'class': 'form-control'})
            match f:
                case forms.DateTimeField():
                    f.widget = WidgetDateTime()
                case forms.Field(choices=c):
                    if len(c) > 0:
                        attrs['class'] = 'form-select'
            f.widget.attrs.update(attrs)
            field_widgets[k.split('_')[-1]] = f.widget
        self.widget = WidgetOBElement(field_widgets)
        super().__init__(error_messages=error_messages, fields=fields, require_all_fields=False, **kwargs)

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
    def get_initial_for_field(self, field, field_name):
        name = field_name.split(self.prefix)[-1]
        ob_element = obit.OBElement(name)
        return {p.name: getattr(self.initial, f'{name}_{p.name}')
                for p in ob_element.primitives()}


class Dimension(Form):
    pass


class Product(Form):
    pass


class ProdCell(Form):
    pass


class ProdGlazing(Form):
    pass


class ProdModule(Product):
    pass
