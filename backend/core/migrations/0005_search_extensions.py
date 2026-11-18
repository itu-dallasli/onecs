from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0004_orgnode_is_demo_user_profile_kind")]
    operations = [UnaccentExtension(), TrigramExtension()]
