"""Test measures module."""


def test_apply_measure_to_whole_library():
    from archetypal import EnergyStarUpgrade, UmiTemplateLibrary

    umi = UmiTemplateLibrary.open(
        "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"
    )

    assert umi.BuildingTemplates[0].Core.Loads.EquipmentPowerDensity == 8.0

    # apply the measure
    EnergyStarUpgrade().apply_measure_to_whole_library(umi)

    assert umi.BuildingTemplates[0].Core.Loads.EquipmentPowerDensity == 3
