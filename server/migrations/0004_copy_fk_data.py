"""
Phase B: Data migration — copy FK values from junction tables and old FK columns
into the new FK columns added in 0003.
"""
from django.db import migrations


def copy_fk_data(apps, schema_editor):
    """Copy relationship data from old fields/junction tables to new FK columns."""
    connection = schema_editor.connection
    cursor = connection.cursor()

    # --- OneToOne reversals: copy FK from parent to dependent model ---

    # Product.Dimension -> Dimension.Product
    cursor.execute("""
        UPDATE server_dimension SET Product_id = (
            SELECT p.id FROM server_product p WHERE p.Dimension_id = server_dimension.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_product p WHERE p.Dimension_id = server_dimension.id
        )
    """)

    # Package.Dimension -> Dimension.Package
    cursor.execute("""
        UPDATE server_dimension SET Package_id = (
            SELECT pk.id FROM server_package pk WHERE pk.Dimension_id = server_dimension.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_package pk WHERE pk.Dimension_id = server_dimension.id
        )
    """)

    # ProdBattery.DCInput -> DCInput.ProdBattery
    cursor.execute("""
        UPDATE server_dcinput SET ProdBattery_id = (
            SELECT pb.product_ptr_id FROM server_prodbattery pb
            WHERE pb.DCInput_id = server_dcinput.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_prodbattery pb
            WHERE pb.DCInput_id = server_dcinput.id
        )
    """)

    # ProdBattery.DCOutput -> DCOutput.ProdBattery
    cursor.execute("""
        UPDATE server_dcoutput SET ProdBattery_id = (
            SELECT pb.product_ptr_id FROM server_prodbattery pb
            WHERE pb.DCOutput_id = server_dcoutput.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_prodbattery pb
            WHERE pb.DCOutput_id = server_dcoutput.id
        )
    """)

    # ProdModule.ProdGlazing -> ProdGlazing.ProdModule
    cursor.execute("""
        UPDATE server_prodglazing SET ProdModule_id = (
            SELECT pm.product_ptr_id FROM server_prodmodule pm
            WHERE pm.ProdGlazing_id = server_prodglazing.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_prodmodule pm
            WHERE pm.ProdGlazing_id = server_prodglazing.id
        )
    """)

    # ProdCertification.Firmware -> Firmware.ProdCertification
    cursor.execute("""
        UPDATE server_firmware SET ProdCertification_id = (
            SELECT pc.id FROM server_prodcertification pc
            WHERE pc.Firmware_id = server_firmware.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_prodcertification pc
            WHERE pc.Firmware_id = server_firmware.id
        )
    """)

    # Firmware.Checksum -> Checksum.Firmware
    cursor.execute("""
        UPDATE server_checksum SET Firmware_id = (
            SELECT f.id FROM server_firmware f
            WHERE f.Checksum_id = server_checksum.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_firmware f
            WHERE f.Checksum_id = server_checksum.id
        )
    """)

    # Contact.Address -> Address.Contact
    cursor.execute("""
        UPDATE server_address SET Contact_id = (
            SELECT c.id FROM server_contact c
            WHERE c.Address_id = server_address.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_contact c
            WHERE c.Address_id = server_address.id
        )
    """)

    # Comment.Scope -> Scope.Comment
    cursor.execute("""
        UPDATE server_scope SET Comment_id = (
            SELECT cm.id FROM server_comment cm
            WHERE cm.Scope_id = server_scope.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_comment cm
            WHERE cm.Scope_id = server_scope.id
        )
    """)

    # Address.Location -> Location.Address
    cursor.execute("""
        UPDATE server_location SET Address_id = (
            SELECT a.id FROM server_address a
            WHERE a.Location_id = server_location.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_address a
            WHERE a.Location_id = server_location.id
        )
    """)

    # Scope.Location -> Location.Scope
    cursor.execute("""
        UPDATE server_location SET Scope_id = (
            SELECT s.id FROM server_scope s
            WHERE s.Location_id = server_location.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_scope s
            WHERE s.Location_id = server_location.id
        )
    """)

    # --- M2M -> FK: copy from junction tables ---

    # Product.ProdCertifications M2M -> ProdCertification.Product FK
    cursor.execute("""
        UPDATE server_prodcertification SET Product_id = (
            SELECT jt.product_id FROM server_product_ProdCertifications jt
            WHERE jt.prodcertification_id = server_prodcertification.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_product_ProdCertifications jt
            WHERE jt.prodcertification_id = server_prodcertification.id
        )
    """)

    # Product.SourceCountries M2M -> SourceCountry.Product FK
    cursor.execute("""
        UPDATE server_sourcecountry SET Product_id = (
            SELECT jt.product_id FROM server_product_SourceCountries jt
            WHERE jt.sourcecountry_id = server_sourcecountry.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_product_SourceCountries jt
            WHERE jt.sourcecountry_id = server_sourcecountry.id
        )
    """)

    # ProdModule.ModuleElectRatings M2M -> ModuleElectRating.ProdModule FK
    cursor.execute("""
        UPDATE server_moduleelectrating SET ProdModule_id = (
            SELECT jt.prodmodule_id FROM server_prodmodule_ModuleElectRatings jt
            WHERE jt.moduleelectrating_id = server_moduleelectrating.id
        )
        WHERE EXISTS (
            SELECT 1 FROM server_prodmodule_ModuleElectRatings jt
            WHERE jt.moduleelectrating_id = server_moduleelectrating.id
        )
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0003_remove_product_alternativeidentifiers_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=migrations.RunSQL.noop,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(copy_fk_data, migrations.RunPython.noop),
    ]
