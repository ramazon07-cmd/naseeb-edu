"""Delete stored files when their rows are deleted.

Covers every model with a FileField/ImageField in the admissions and users
apps, including rows removed by cascades (deleting a student account removes
its documents, evidence, recommendations and photo). Files are removed only
after the transaction commits, so a rolled-back delete keeps its files.
"""
from django.apps import apps
from django.db import models
from django.db.models.signals import post_delete
from core.storage import delete_file_on_commit

FILE_APPS = ('admissions', 'users')


def file_fields(model):
    return [field for field in model._meta.get_fields() if isinstance(field, models.FileField)]


def delete_files_on_row_delete(sender, instance, **kwargs):
    for field in file_fields(sender):
        file = getattr(instance, field.name, None)
        name = getattr(file, 'name', '')
        if name:
            delete_file_on_commit(file.storage, name)


def connect():
    for label in FILE_APPS:
        for model in apps.get_app_config(label).get_models():
            if file_fields(model):
                post_delete.connect(
                    delete_files_on_row_delete,
                    sender=model,
                    dispatch_uid=f'delete-files-{model._meta.label_lower}',
                )
