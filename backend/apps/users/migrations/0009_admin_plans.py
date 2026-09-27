import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0044_merge_0038_essay_lab_0043_audit_indexes"),
        ("users", "0008_admin_superuser_manager"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=60, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("max_counselors", models.PositiveIntegerField(blank=True, null=True)),
                ("max_students", models.PositiveIntegerField(blank=True, null=True)),
                ("max_teachers", models.PositiveIntegerField(blank=True, null=True)),
                ("features", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="WorkspaceSubscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("trial", "Trial"),
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("expired", "Expired"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="workspacesubscription",
            name="plan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="users.plan",
            ),
        ),
        migrations.AddField(
            model_name="workspacesubscription",
            name="school",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscription",
                to="admissions.school",
            ),
        ),
        migrations.AddField(
            model_name="workspacesubscription",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="workspacesubscription",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("period_start__isnull", True),
                    ("period_end__isnull", True),
                    ("period_end__gte", models.F("period_start")),
                    _connector="OR",
                ),
                name="subscription_period_order",
            ),
        ),
    ]
