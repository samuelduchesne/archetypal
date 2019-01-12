import glob

import pytest

import archetypal as ar

# configure archetypal
ar.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../data/BostonTemplateLibrary.json')

files_to_try = ['./input_data/problematic/*.idf',
                './input_data/regular/*.idf',
                './input_data/umi_samples/*.idf']
ids = ['problematic', 'regular', 'umi_samples']


@pytest.fixture(scope='module', params=files_to_try, ids=ids)
def template(fresh_start, request):
    """Instantiate an umi template placeholder. Calls in the fresh_start
    function to clear the cache folder"""
    idf = glob.glob(request.param)
    idf = ar.copy_file(idf)
    # idf = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = ar.Template(idf, wf)

    yield a


@pytest.fixture(scope='module')
def sql(template):
    sql = template.run_eplus(silent=False, processors=-1, prep_outputs=True,
                             expandobjects=True, design_day=True)
    yield sql


def test_materials_gas(template):
    template.materials_gas = ar.materials_gas(template.idfs)
    assert not template.materials_gas.empty


def test_materials_glazing(template):
    template.materials_glazing = ar.materials_glazing(template.idfs)
    template.materials_glazing = ar.newrange(template.materials_gas,
                                             template.materials_glazing)
    return template.materials_glazing


def test_materials_opaque(template):
    template.materials_opaque = ar.materials_opaque(template.idfs)
    template.materials_opaque = ar.newrange(template.materials_glazing,
                                            template.materials_opaque)
    return template.materials_opaque


def test_constructions_opaque(template):
    template.constructions_opaque = ar.constructions_opaque(template.idfs,
                                                            template.materials_opaque)
    template.constructions_opaque = ar.newrange(template.materials_opaque,
                                                template.constructions_opaque)
    return template.constructions_opaque


def test_constructions_windows(template):
    template.constructions_windows = ar.constructions_windows(template.idfs,
                                                              template.materials_glazing)
    template.constructions_windows = ar.newrange(template.constructions_opaque,
                                                 template.constructions_windows)
    return template.constructions_windows


def test_day_schedules(template):
    template.day_schedules = ar.day_schedules(template.idfs)
    return template.day_schedules


def test_week_schedules(template):
    template.week_schedules = ar.week_schedules(template.idfs,
                                                template.day_schedules)
    template.week_schedules = ar.newrange(template.day_schedules,
                                          template.week_schedules)
    return template.week_schedules


def test_year_schedules(template):
    template.year_schedules = ar.year_schedules(template.idfs,
                                                template.week_schedules)
    template.year_schedules = ar.newrange(template.week_schedules,
                                          template.year_schedules)
    return template.year_schedules


# Zones
def test_zone_information(template, sql):
    template.zone_details = ar.zone_information(sql)


def test_zone_loads(template, sql):
    template.zone_loads = ar.zone_loads(sql)


def test_zone_ventilation(template, sql):
    template.zone_ventilation = ar.zone_ventilation(sql)


def test_zone_condition(template, sql):
    template.zone_conditioning = ar.zone_conditioning(sql)
