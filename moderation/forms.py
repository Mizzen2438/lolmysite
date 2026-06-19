from django import forms

from .models import Report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "detail"]
        widgets = {
            "reason": forms.RadioSelect,
            "detail": forms.Textarea(
                attrs={"rows": 3, "placeholder": "状況を具体的にご記入ください(任意)"}
            ),
        }
