# Generated by Django 5.1 on 2025-04-30 17:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mix_and_match', '0003_outfitairesult'),
    ]

    operations = [
        migrations.AddField(
            model_name='outfititem',
            name='modified_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='useroutfit',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
