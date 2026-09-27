from django.db import migrations


def create_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE SEQUENCE IF NOT EXISTS account_number_seq START WITH 1 INCREMENT BY 1;
            """)
            cursor.execute("""
                SELECT setval(
                    'account_number_seq',
                    COALESCE(
                        (SELECT MAX(CAST(SUBSTRING(account_number FROM 4) AS INTEGER))
                         FROM accounts_account
                         WHERE account_number LIKE 'ACC%'),
                        0
                    ) + 1,
                    false
                );
            """)


def drop_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("DROP SEQUENCE IF EXISTS account_number_seq;")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_sequence, reverse_code=drop_sequence),
    ]
