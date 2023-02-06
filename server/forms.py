from django import forms

from server import ob_item_types as obit


class WidgetOBElement(forms.MultiWidget):
    template_name = 'server/forms/widgets/multiwidget_obelement.html'

    def __init__(self, editable=True, attrs=None):
        widgets = dict(
            Value=forms.TextInput(),
            Unit=forms.TextInput(),
            StartTime=forms.TextInput(),
            EndTime=forms.TextInput(),
            Decimals=forms.TextInput(),
            Precision=forms.TextInput()
        )
        self.editable = editable
        super().__init__(widgets, attrs)

    def get_context(self, name, value, attrs):
        values_list = []
        prims = set(p.name for p in obit.OBElement(name).primitives())
        for wn in self.widgets_names:
            if (p := wn[1:]) in prims and (v := value[p]) is not None:
                values_list.append(v)
            else:
                values_list.append('')
        context = super().get_context(name, values_list, attrs)
        context['editable'] = self.editable
        context['widget']['subwidgets_dict'] = {
            prim[1:]: sw_context
            for prim, sw_context in zip(self.widgets_names, context['widget']['subwidgets'])
        }
        print(context)
        return context

    def decompress(self, value):
        return [''] * 2

    def render(self, name, value, attrs=None, renderer=None):
        if self.editable:
            pass
        r = super().render(name, value, attrs=attrs, renderer=renderer)
        print(r)
        return r


class OBElement(forms.MultiValueField):
    widget = WidgetOBElement

    def __init__(self, **kwargs,):  # required, label, initil, widget, help_text):
        error_messages = dict(err='err')
        fields = (forms.CharField(label='Value', max_length=10), forms.CharField(label='Unit', max_length=10))
        super().__init__(error_messages=error_messages, fields=fields, require_all_fields=False, **kwargs)

    def compress(self, data_list):
        pass


class ProdModule(forms.Form):
    # Description = forms.CharField(label='Description', max_length=10)
    Description = OBElement(label='Description')
    ProdID = OBElement(label='Description')

    def get_initial_for_field(self, field, field_name):
        ob_element = obit.OBElement(field_name)
        prodmodule = self.initial
        return {p.name: getattr(prodmodule, f'{field_name}_{p.name}')
                for p in ob_element.primitives()}
