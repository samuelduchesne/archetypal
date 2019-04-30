from archetypal import load_umi_template, copy_file, UmiTemplate, settings, \
    run_eplus


# def test_load_umi_template(config):
#     data_json = settings.umitemplate
#     assert len(load_umi_template(data_json)) == 17

def test_template_to_template():
    file = '../data/BostonTemplateLibrary.json'
    template = UmiTemplate.from_json(file)

    print(template)
    # read a template library



def test_umi_routine(config):
    idf_source = [
        './input_data/necb/NECB 2011-FullServiceRestaurant-NECB HDD '
        'Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf',
        './input_data/necb/NECB 2011-LargeHotel-NECB HDD '
        'Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf',
        './input_data/umi_samples/VentilationSimpleTest.idf'
    ]
    idf = copy_file(idf_source)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = UmiTemplate(idf, wf, load=True, run_eplus_kwargs=dict(
        prep_outputs=True), name='Mixed_Files')
    print(a.building_templates)

    print(a.to_json())


def test_umi_samples(config):
    idf_source = ['./input_data/umi_samples/B_Off_0.idf',
                  './input_data/umi_samples/B_Ret_0.idf',
                  './input_data/umi_samples/B_Res_0_Masonry.idf',
                  './input_data/umi_samples/B_Res_0_WoodFrame.idf']
    idf_source = copy_file(idf_source)
    # run_eplus(idf_source, weather_file='./input_data/CAN_PQ_Montreal.Intl.AP'
    #                                    '.716270_CWEC.epw')
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    a = UmiTemplate(idf_source, wf, load=True, run_eplus_kwargs=dict(
        prep_outputs=True, expandobjects=True), name='Umi_Samples')
    print(a.building_templates)

    print(a.to_json())
