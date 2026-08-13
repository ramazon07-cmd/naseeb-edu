import mimetypes
import shutil
from pathlib import Path

import apps.admissions.models
from django.conf import settings
from django.db import migrations, models


def move_existing_evidence_to_private_storage(apps, schema_editor):
    public_root = Path(settings.MEDIA_ROOT).resolve()
    private_root = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    for model_name in ('Achievement', 'Honor'):
        Model = apps.get_model('admissions', model_name)
        for record in Model.objects.exclude(proof_file='').exclude(proof_file__isnull=True).iterator():
            relative_name = record.proof_file.name
            source = (public_root / relative_name).resolve()
            destination = (private_root / relative_name).resolve()
            if (
                source.is_relative_to(public_root)
                and destination.is_relative_to(private_root)
                and source.exists()
            ):
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copy2(source, destination)
            existing_file = destination if destination.exists() else source
            original_name = Path(relative_name).name
            Model.objects.filter(pk=record.pk).update(
                proof_file_name=original_name[:255],
                proof_file_content_type=(
                    mimetypes.guess_type(original_name)[0] or 'application/octet-stream'
                )[:120],
                proof_file_size=existing_file.stat().st_size if existing_file.exists() else 0,
            )
            if public_root != private_root and destination.exists() and source.exists():
                source.unlink()


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0023_counselorroadmaptemplate_counselorroadmap_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='achievement',
            name='proof_file_content_type',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='achievement',
            name='proof_file_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='achievement',
            name='proof_file_size',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='honor',
            name='proof_file_content_type',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='honor',
            name='proof_file_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='honor',
            name='proof_file_size',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.RunPython(
            move_existing_evidence_to_private_storage,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='achievement',
            name='proof_file',
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.admissions.models.PrivateDocumentStorage(),
                upload_to=apps.admissions.models.student_evidence_upload_path,
            ),
        ),
        migrations.AlterField(
            model_name='honor',
            name='proof_file',
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.admissions.models.PrivateDocumentStorage(),
                upload_to=apps.admissions.models.student_evidence_upload_path,
            ),
        ),
    ]
