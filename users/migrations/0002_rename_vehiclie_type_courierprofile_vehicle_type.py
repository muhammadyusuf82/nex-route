# Generated manually for vehiclie_type → vehicle_type rename

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='courierprofile',
            old_name='vehiclie_type',
            new_name='vehicle_type',
        ),
    ]
