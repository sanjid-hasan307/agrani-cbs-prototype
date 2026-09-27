from django.db import migrations


def create_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE SEQUENCE IF NOT EXISTS transaction_id_seq START WITH 1 INCREMENT BY 1;
            """)
            cursor.execute("""
                SELECT setval(
                    'transaction_id_seq',
                    COALESCE(
                        (SELECT MAX(CAST(SUBSTRING(transaction_id FROM 4) AS INTEGER))
                         FROM transactions_transaction
                         WHERE transaction_id LIKE 'TXN%'),
                        0
                    ) + 1,
                    false
                );
            """)


def drop_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("DROP SEQUENCE IF EXISTS transaction_id_seq;")


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_sequence, reverse_code=drop_sequence),
    ]
