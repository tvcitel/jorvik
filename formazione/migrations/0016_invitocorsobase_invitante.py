# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-10-16 08:50
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('anagrafica', '0041_auto_20160513_0954'),
        ('formazione', '0015_invitocorsobase'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitocorsobase',
            name='invitante',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='anagrafica.Persona'),
            preserve_default=False,
        ),
    ]
