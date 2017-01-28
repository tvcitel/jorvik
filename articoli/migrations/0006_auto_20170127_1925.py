# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-01-27 19:25
from __future__ import unicode_literals

import autoslug.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('articoli', '0005_auto_20161018_2201'),
    ]

    operations = [
        migrations.AlterField(
            model_name='articolo',
            name='slug',
            field=autoslug.fields.AutoSlugField(always_update=True, editable=False, max_length=255, null=True, populate_from='titolo', unique=True),
        ),
    ]
