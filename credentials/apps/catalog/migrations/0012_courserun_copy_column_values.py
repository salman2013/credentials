# -*- coding: utf-8 -*-
# Generated by Django 1.11.25 on 2019-11-01 17:04
from __future__ import unicode_literals

from django.db import migrations


def copy_column_values_forwards(apps, schema_editor):
    """
    Copy the start and end fields into the start_date and end_date fields respectively.

    This table should have a few thousand rows at most, so I'm not so concerned about long-term
    database locking.
    """
    CourseRun = apps.get_model('catalog', 'CourseRun')
    for course_run in CourseRun.objects.all():
        course_run.start_date = course_run.start
        course_run.end_date = course_run.end
        course_run.save()


def copy_column_values_backwards(apps, schema_editor):
    """
    We must specify a backwards migration even if it is empty, or else django will raise an
    exception if we try to rollback this migration.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_add_new_start_date_end_date_fields'),
    ]

    operations = [
        migrations.RunPython(
            copy_column_values_forwards,
            copy_column_values_backwards,
        ),
    ]
