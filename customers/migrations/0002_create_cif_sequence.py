from django.db import migrations


def create_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE SEQUENCE IF NOT EXISTS customer_cif_seq START WITH 1 INCREMENT BY 1;
            """)
            cursor.execute("""
                SELECT setval(
                    'customer_cif_seq',
                    COALESCE(
                        (SELECT MAX(CAST(SUBSTRING(cif_number FROM 4) AS INTEGER)) 
                         FROM customers_customer 
                         WHERE cif_number LIKE 'CIF%'),
                        0
                    ) + 1,
                    false
                );
            """)


def drop_sequence(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("DROP SEQUENCE IF EXISTS customer_cif_seq;")


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_sequence, reverse_code=drop_sequence),
    ]
