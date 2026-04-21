from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0009_sitesettings'),
    ]

    operations = [
        migrations.RenameField(
            model_name='sitesettings',
            old_name='workato_webhook_url',
            new_name='webhook_url',
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='webhook_url',
            field=models.URLField(
                blank=True,
                help_text=(
                    'Webhook URL for forwarding submissions. Any HTTP endpoint '
                    '(Workato recipe, Zapier, n8n, custom service). Blank = do not post.'
                ),
                max_length=500,
            ),
        ),
    ]
