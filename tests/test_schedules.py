from archetypal import Schedule, load_idf


def test_day_schedule(config):
    """Tests all schedules in the schedule.idf file"""
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)

    for obj in idf['schedules.idf'].idfobjects:
        for bunch in idf['schedules.idf'].idfobjects[obj]:
            try:
                s = Schedule(idf['schedules.idf'], sch_name=bunch.Name,
                             start_day_of_the_week=idf[
                                 'schedules.idf'].day_of_week_for_start_day)

                values = s.get_schedule_values()
                print('{name}\tType:{type}\t[{len}]\tValues:{'
                      'values}'.format(
                    name=s.schName,
                    type=s.schType,
                    values=values,
                    len=len(values)))
            except:
                pass


def test_file_schedule(config):
    """Tests only 'elecTDVfromCZ06com' schedule name"""
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, sch_name='POFF')

    assert len(s.all_values) == 8760


def test_schedules_in_necb(config):
    idf_file = './input_data/regular/NECB 2011-MediumOffice-NECB HDD ' \
               'Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf'
    idfs = load_idf(idf_file)
    for key in idfs:
        idf = idfs[key]
        # get all possible shcedules
        schedules = idf.get_all_schedules()
        for sched in schedules:
            schedules[sched] = Schedule(idf, sch_name=sched).all_values
        print(schedules)


def test_schedules_in_necb_specific(config):
    idf_file = './input_data/regular/NECB 2011-MediumOffice-NECB HDD ' \
               'Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf'
    idfs = load_idf(idf_file)
    import matplotlib.pyplot as plt
    for key in idfs:
        idf = idfs[key]
        s = Schedule(idf, sch_name='NECB-A-Thermostat Setpoint-Heating',
                     start_day_of_the_week=0)
        s.plot(slice=('2018/01/02', '2018/01/03'), drawstyle="steps-post")
        plt.show()


def test_make_umi_schedule(config):
    """Tests only 'elecTDVfromCZ06com' schedule name"""
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, sch_name='On Peak 2')
    ep_objs = s.to_year_week_day()

    assert len(s.all_values) == 8760
