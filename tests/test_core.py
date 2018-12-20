import glob

import pytest

import pyumi as pu

# configure pyumi
pu.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../data/BostonTemplateLibrary.json')


@pytest.fixture(scope='module')
def template(cleanup):
    """Instantiate an umi template placeholder. Calls in the cleanup function to
    clear the cache folder"""
    idf = glob.glob('./input_data/*.idf')
    # idf = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = pu.Template(idf, wf)

    yield a


def test_materials_gas(template):
    template.materials_gas = pu.materials_gas(template.idfs)
    assert not template.materials_gas.empty


def test_materials_glazing(template):
    template.materials_glazing = pu.materials_glazing(template.idfs)
    template.materials_glazing = pu.newrange(template.materials_gas, template.materials_glazing)
    return template.materials_glazing


def test_materials_opaque(template):
    template.materials_opaque = pu.materials_opaque(template.idfs)
    template.materials_opaque = pu.newrange(template.materials_glazing, template.materials_opaque)
    return template.materials_opaque


def test_constructions_opaque(template):
    template.constructions_opaque = pu.constructions_opaque(template.idfs, template.materials_opaque)
    template.constructions_opaque = pu.newrange(template.materials_opaque, template.constructions_opaque)
    return template.constructions_opaque


def test_constructions_windows(template):
    template.constructions_windows = pu.constructions_windows(template.idfs, template.materials_glazing)
    template.constructions_windows = pu.newrange(template.constructions_opaque, template.constructions_windows)
    return template.constructions_windows


def test_day_schedules(template):
    template.day_schedules = pu.day_schedules(template.idfs)
    return template.day_schedules


def test_week_schedules(template):
    template.week_schedules = pu.week_schedules(template.idfs, template.day_schedules)
    template.week_schedules = pu.newrange(template.day_schedules, template.week_schedules)
    return template.week_schedules


def test_year_schedules(template):
    template.year_schedules = pu.year_schedules(template.idfs, template.week_schedules)
    template.year_schedules = pu.newrange(template.week_schedules, template.year_schedules)
    return template.year_schedules
