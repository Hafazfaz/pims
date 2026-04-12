from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('document_management', '0016_alter_document_status'),
        ('organization', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FileMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.TextField(blank=True, default='')),
                ('moved_at', models.DateTimeField(auto_now_add=True)),
                ('action', models.CharField(default='sent', max_length=20)),
                ('file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movements', to='document_management.file')),
                ('from_location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outgoing_movements', to='organization.staff')),
                ('sent_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_movements', to=settings.AUTH_USER_MODEL)),
                ('sent_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='received_movements', to='organization.staff')),
            ],
            options={
                'ordering': ['-moved_at'],
            },
        ),
    ]
