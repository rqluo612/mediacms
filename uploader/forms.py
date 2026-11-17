from django import forms

from .metadata import validate_metadata


class UploadMetadataForm(forms.Form):
    qquuid = forms.UUIDField()
    title = forms.CharField(required=False)
    description = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    def clean_qquuid(self):
        value = self.cleaned_data["qquuid"]
        if value.version != 4:
            raise forms.ValidationError("上传标识必须是有效的 UUID v4。")
        return value

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        metadata = validate_metadata(self.data, data.get("qqfilename", ""))
        data.update(metadata)
        data["qquuid"] = str(data["qquuid"])
        return data


class FineUploaderUploadForm(UploadMetadataForm):
    qqfile = forms.FileField()
    qqfilename = forms.CharField()
    qqpartindex = forms.IntegerField(required=False)
    qqchunksize = forms.IntegerField(required=False)
    qqtotalparts = forms.IntegerField(required=False)
    qqtotalfilesize = forms.IntegerField(required=False)
    qqpartbyteoffset = forms.IntegerField(required=False)


class FineUploaderUploadSuccessForm(UploadMetadataForm):
    qqfilename = forms.CharField()
    qqtotalparts = forms.IntegerField()
    qqtotalfilesize = forms.IntegerField(required=False)
