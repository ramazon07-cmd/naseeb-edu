import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0044_merge_0038_essay_lab_0043_audit_indexes"),
        ("users", "0010_admin_seed_plans"),
    ]

    operations = [
        migrations.AddField(
            model_name="productauditevent",
            name="school",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="admissions.school",
            ),
        ),
        migrations.AddIndex(
            model_name="productauditevent",
            index=models.Index(
                fields=["school", "-created_at"], name="product_audit_school_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="productauditevent",
            index=models.Index(
                fields=["actor", "-created_at"], name="product_audit_actor_idx"
            ),
        ),
    ]
