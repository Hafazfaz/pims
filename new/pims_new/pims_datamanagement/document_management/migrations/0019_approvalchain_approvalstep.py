from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('document_management', '0018_filemovement_attachment'),
        ('organization', '0005_staffsignature'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='status',
            field=models.CharField(max_length=20, choices=[("inactive","Inactive"),("pending_activation","Pending Activation"),("active","Active"),("in_transit","In Transit"),("in_review","In Review"),("closed","Closed"),("archived","Archived")], default='inactive'),
            preserve_default=False,
        ) if False else migrations.AlterField(
            model_name='file',
            name='status',
            field=models.CharField(choices=[('inactive', 'Inactive'), ('pending_activation', 'Pending Activation'), ('active', 'Active'), ('in_transit', 'In Transit'), ('in_review', 'In Review'), ('closed', 'Closed'), ('archived', 'Archived')], default='inactive', max_length=20),
        ),
        migrations.CreateModel(
            name='ApprovalChain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('active', 'Active'), ('closed', 'Closed'), ('rejected', 'Rejected')], default='draft', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('current_step', models.PositiveIntegerField(default=1)),
                ('file', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='approval_chain', to='document_management.file')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_chains', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ApprovalStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('note', models.TextField(blank=True)),
                ('actioned_at', models.DateTimeField(blank=True, null=True)),
                ('chain', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='document_management.approvalchain')),
                ('approver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approval_steps', to='organization.staff')),
                ('signature', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='organization.staffsignature')),
            ],
            options={
                'ordering': ['order'],
                'unique_together': {('chain', 'order')},
            },
        ),
    ]
