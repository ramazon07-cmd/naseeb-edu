from django.db import migrations, models


class Migration(migrations.Migration):
    # Separate from 0049 so the backfill commits before PostgreSQL alters the table.

    dependencies = [
        ("admissions", "0049_center_test_scores"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ielts_score__isnull", True),
                    models.Q(("ielts_score__gte", 0), ("ielts_score__lte", 9)),
                    _connector="OR",
                ),
                name="student_ielts_score_band",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ielts_listening__isnull", True),
                    models.Q(("ielts_listening__gte", 0), ("ielts_listening__lte", 9)),
                    _connector="OR",
                ),
                name="student_ielts_listening_band",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ielts_reading__isnull", True),
                    models.Q(("ielts_reading__gte", 0), ("ielts_reading__lte", 9)),
                    _connector="OR",
                ),
                name="student_ielts_reading_band",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ielts_writing__isnull", True),
                    models.Q(("ielts_writing__gte", 0), ("ielts_writing__lte", 9)),
                    _connector="OR",
                ),
                name="student_ielts_writing_band",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ielts_speaking__isnull", True),
                    models.Q(("ielts_speaking__gte", 0), ("ielts_speaking__lte", 9)),
                    _connector="OR",
                ),
                name="student_ielts_speaking_band",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sat_reading__isnull", True),
                    models.Q(("sat_reading__gte", 200), ("sat_reading__lte", 800)),
                    _connector="OR",
                ),
                name="student_sat_reading_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sat_math__isnull", True),
                    models.Q(("sat_math__gte", 200), ("sat_math__lte", 800)),
                    _connector="OR",
                ),
                name="student_sat_math_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sat_superscore_reading__isnull", True),
                    models.Q(
                        ("sat_superscore_reading__gte", 200),
                        ("sat_superscore_reading__lte", 800),
                    ),
                    _connector="OR",
                ),
                name="student_sat_superscore_reading_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sat_superscore_math__isnull", True),
                    models.Q(
                        ("sat_superscore_math__gte", 200),
                        ("sat_superscore_math__lte", 800),
                    ),
                    _connector="OR",
                ),
                name="student_sat_superscore_math_range",
            ),
        ),
    ]
