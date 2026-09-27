from django.db import migrations

BANKING_ROLES = [
    'Admin',
    'Manager',
    'Officer',
    'Teller',
    'Auditor',
]


def create_banking_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for role_name in BANKING_ROLES:
        Group.objects.get_or_create(name=role_name)


def remove_banking_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=BANKING_ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_banking_groups, reverse_code=remove_banking_groups),
    ]
