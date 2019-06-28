import glob
import archetypal as ar
import pytest

# todo: Refactor all tests here to implement the new template logic

ar.config(log_console=True, log_file=True, use_cache=True,
          data_folder='tests/temp/data', logs_folder='tests/temp/logs',
          imgs_folder='tests/temp/imgs', cache_folder='tests/temp/cache',
          umitemplate='tests/input_data/umi_samples/BostonTemplateLibrary_2.json')

# # Uncomment this block to test different file variations
# files_to_try = ['tests/input_data/problematic/*.idf',
#                 'tests/input_data/regular/*.idf',
#                 'tests/input_data/umi_samples/*.idf']
# ids = ['problematic', 'regular', 'umi_samples']

files_to_try = ['tests/input_data/regular/*.idf']
ids = ['regular']


@pytest.fixture(scope='module', params=files_to_try, ids=ids)
def template(fresh_start, request):
    """Instantiate an umi template placeholder. Calls in the fresh_start
    function to clear the cache folder"""
    idf = glob.glob(request.param)
    idf = ar.copy_file(idf)
    # idf = 'tests/input_data/AdultEducationCenter.idf'
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = ar.UmiTemplate.from_idf(idf, wf)

    yield a


@pytest.fixture(scope='session')
def test_template_withcache(config):
    """Instantiate an umi template placeholder. Does note call fresh_start
    function so that caching can be used"""
    idf = glob.glob('tests/input_data/umi_samples/*.idf')
    idf = ar.copy_file(idf)
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = ar.UmiTemplate.from_idf(idf, wf, load=True,
                                run_eplus_kwargs=dict(prep_outputs=True,
                                                      annual=True))

    yield a


@pytest.fixture(scope='module')
def sql(test_template_withcache):
    sql = test_template_withcache.sql
    yield sql


def test_materials_gas(test_template_withcache):
    test_template_withcache.materials_gas = ar.materials_gas(
        test_template_withcache.idfs)
    assert not test_template_withcache.materials_gas.empty


def test_materials_glazing(test_template_withcache):
    test_template_withcache.materials_glazing = ar.materials_glazing(
        test_template_withcache.idfs)
    test_template_withcache.materials_glazing = ar.newrange(
        test_template_withcache.materials_gas,
        test_template_withcache.materials_glazing)
    return test_template_withcache.materials_glazing


def test_materials_opaque(test_template_withcache):
    test_template_withcache.materials_opaque = ar.materials_opaque(
        test_template_withcache.idfs)
    test_template_withcache.materials_opaque = ar.newrange(
        test_template_withcache.materials_glazing,
        test_template_withcache.materials_opaque)
    return test_template_withcache.materials_opaque


def test_constructions_opaque(test_template_withcache):
    test_template_withcache.constructions_opaque = ar.constructions_opaque(
        test_template_withcache.idfs,
        test_template_withcache.materials_opaque)
    test_template_withcache.constructions_opaque = ar.newrange(
        test_template_withcache.materials_opaque,
        test_template_withcache.constructions_opaque)
    return test_template_withcache.constructions_opaque


def test_constructions_windows(test_template_withcache):
    test_template_withcache.constructions_windows = ar.constructions_windows(
        test_template_withcache.idfs,
        test_template_withcache.materials_glazing)
    test_template_withcache.constructions_windows = ar.newrange(
        test_template_withcache.constructions_opaque,
        test_template_withcache.constructions_windows)
    return test_template_withcache.constructions_windows


# Zone
def test_zone_information(test_template_withcache, sql):
    template.zone_details = ar.zone_information(sql)


def test_zone_loads(test_template_withcache, sql):
    template.zone_loads = ar.zone_loads(sql)


def test_zone_ventilation(test_template_withcache, sql):
    template.zone_ventilation = ar.zone_ventilation(sql)


def test_zone_condition(test_template_withcache, sql):
    template.zone_conditioning = ar.zone_conditioning(sql)


def test_zone_condition_dev(test_template_withcache, sql):
    test_template_withcache.zone_conditioning = ar.zone_conditioning(sql)
    print(test_template_withcache.zone_conditioning)


def test_zone_dhw(test_template_withcache, sql):
    test_template_withcache.domestic_hot_water_settings = \
        ar.zone_domestic_hot_water_settings(sql, test_template_withcache.idfs)
    print(test_template_withcache.domestic_hot_water_settings)


def test_to_json(test_template_withcache):
    json = test_template_withcache.to_json()
    print(json)


def test_to_json_std(config):
    files = glob.glob("tests/input_data/necb/*Office*idf")
    files = ar.copy_file(files)[1:4]
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = ar.UmiTemplate.from_idf(files, wf)
    json = a.to_json()
    print(json)


def test_parse_schedule_profile():
    idf = 'tests/input_data/regular/5ZoneNightVent1.idf'
    outputs = {'ep_object': 'Output:Variable'.upper(),
               'kwargs': {'Key_Value': 'OCCUPY-1',
                          'Variable_Name': 'Schedule Value',
                          'Reporting_Frequency': 'Hourly'}}
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    idf = ar.copy_file(idf)
    sql = ar.run_eplus(idf, weather_file=wf, prep_outputs=[outputs],
                       annual=True, output_report='sql')
    report = ar.get_from_reportdata(sql)
    array = report.loc[(report.Name == 'Schedule Value') &
                       (report['KeyValue'] == 'OCCUPY-1')].sort_values(
        by="TimeIndex").Value
    # return a list of arrays of 24 hours length
    days = array.reset_index(drop=True).groupby(lambda x: x // 24).apply(
        lambda x: x.values)

    unique_day = {}
    for i, day in days.iteritems():
        hashed_day = str(day)
        thisday = unique_day.get(hashed_day, None)
        if thisday is None:
            unique_day[hashed_day] = (i, day)


