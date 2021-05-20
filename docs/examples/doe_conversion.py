"""Conversion Script tailored to DOE Commercial Reference Buildings."""

import os

from path import Path

from archetypal.umi_template import UmiTemplateLibrary

if __name__ == "__main__":

    basepath = Path(
        r"C:\Users\samueld\Dropbox (Personal)\MIT\PostDoc\research\umiverse\template library\usa"
    )
    zone = "6A"

    os.chdir(basepath / zone)
    epw = next(
        iter(Path(rf"../refbldgs-v1.3_5.0-weather_files_tmy2").files(f"{zone}*.epw"))
    )

    # Change the template list with names of archetypes to convert
    templates = [
        "StripMall",
        "Stand-aloneRetail",
        "Warehouse",
        "MediumOffice",
        "MidriseApartment",
        "FullServiceRestaurant",
        "Supermarket",
        "Hospital",
    ]

    # Create the list if file paths
    idf_files = []
    for name in templates:
        idf_files.extend(Path(".").files(f"*{name}*.idf"))

    # Create the Template Library File
    umi = UmiTemplateLibrary.from_idf_files(
        idf_files, weather=epw, name=f"refbldgs_{zone}", processors=-1
    )

    # Adjust metadata
    for template in umi.BuildingTemplates:
        name = next(filter(lambda x: x in template.Name, templates))  # StripMall
        # set year
        if "Pre1980" in template.Name:
            vintage = "Pre1980"
            template.YearFrom = 0
            template.YearTo = 1980
        elif "Post1980" in template.Name:
            vintage = "Post1980"
            template.YearFrom = 1980
            template.YearTo = 2004
        elif "New2004" in template.Name:
            vintage = "New2004"
            template.YearFrom = 2004
            template.YearTo = 9999
        else:
            raise ValueError("Vintage cloud not be defined")
        # set CZ & Country
        template.ClimateZone = [f"{zone}"]
        template.Country = ["USA"]
        template.Name = "_".join(map(str, [name, vintage, zone]))

    # Save the template library file
    umi.save()
