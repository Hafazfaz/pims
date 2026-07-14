from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("document_management", "0039_document_priority_documentsignature"),
    ]

    operations = [
        migrations.AddField(
            model_name="file",
            name="is_sensitive",
            field=models.BooleanField(
                default=False,
                help_text="Mark as sensitive. Only HODs, Supervisors, Executives, and MD can view document contents.",
            ),
        ),
    ]
