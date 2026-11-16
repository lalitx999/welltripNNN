from django.db import migrations


def repin(apps, schema_editor):
    """
    Pins saved from Google Maps place links used the map centre ("@lat,lng");
    move them to the place's own pin ("!3d..!4d..") when the saved link has it.
    """
    from apps.core.geo import parse_coordinates

    for model in (apps.get_model("community", "MapLocation"), apps.get_model("accommodations", "Accommodation")):
        for obj in model.objects.filter(google_maps_url__contains="!3d"):
            lat, lng = parse_coordinates(obj.google_maps_url)
            if lat is not None and (obj.latitude, obj.longitude) != (lat, lng):
                obj.latitude, obj.longitude = lat, lng
                obj.save(update_fields=["latitude", "longitude"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_report_adjustment"),
        ("community", "0007_eventimage"),
        ("accommodations", "0003_house_cooling_pricing_profile"),
    ]
    operations = [migrations.RunPython(repin, migrations.RunPython.noop)]
