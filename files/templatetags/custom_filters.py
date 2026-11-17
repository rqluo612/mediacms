from django import template

from files.frontend_translations import translate_string

register = template.Library()


@register.filter
def custom_translate(string, lang_code):
    return translate_string(lang_code, string)


@register.simple_tag
def upload_metadata_version():
    """Invalidate the upload module URL whenever its served contents change."""
    import hashlib
    from pathlib import Path
    from django.conf import settings

    return hashlib.sha256((Path(settings.STATIC_ROOT) / 'js/upload-metadata.js').read_bytes()).hexdigest()[:16]
