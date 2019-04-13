from archetypal import Schedule, load_idf, copy_file
import time

def test_day_schedule(config):
    """Tests all schedules in the schedule.idf file"""
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)

    scheds = idf['schedules.idf'].get_all_schedules()

    for sched in scheds:
        s = Schedule(idf['schedules.idf'], sch_name=scheds[sched].Name)
        values = s.all_values
        print('{name}\tType:{type}\t[{len}]\tValues:{'
              'values}'.format(
            name=s.schName,
            type=s.schType,
            values=values,
            len=len(values)))


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
        # get all possible schedules
        schedules = idf.get_all_schedules()
        for sched in schedules:
            s = Schedule(idf, sch_name=sched)
            values = s.all_values
            print('{name}\tType:{type}\t[{len}]\tValues:{'
                  'values}'.format(
                name=s.schName,
                type=s.schType,
                values=values,
                len=len(values)))


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
    """Tests only a single schedule name"""
    import matplotlib.pyplot as plt
    idf_file = './input_data/schedules/schedules.idf'
    idf_file = copy_file(idf_file)[0]
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, sch_name='POFF',
                 start_day_of_the_week=0)
    ep_year, ep_weeks, ep_days = s.to_year_week_day()

    new = Schedule(idf, sch_name=ep_year.Name,
                   start_day_of_the_week=s.startDayOfTheWeek)

    print(len(s.all_values))
    print(len(new.all_values))
    ax = s.plot(slice=('2018/01/01 00:00', '2018/01/07'), legend=True)
    new.plot(slice=('2018/01/01 00:00', '2018/01/07'), ax=ax, legend=True)
    plt.show()
    print((s != new).sum())
    assert len(s.all_values) == len(new.all_values)
    assert (new.all_values == s.all_values).all()


def test_ep_versus_shedule(config):
    import pandas as pd
    import matplotlib.pyplot as plt

    idf_file = './input_data/schedules/schedules.idf'
    idf_file = copy_file(idf_file)[0]
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, sch_name='POFF',
                 start_day_of_the_week=1)
    index = s.series.index
    epv = pd.read_csv('./input_data/schedules/output_EP.csv').loc[:, 'POFF'].values
    epv = pd.Series(epv, index=index)

    slice_ = ('2018/04/30 12:00', '2018/05/02 16:00')
    diff = (epv.values != s.all_values).sum()
    ax = epv.loc[slice_[0]:slice_[1]].plot(label='E+', legend=True,
                                           drawstyle='steps-post')
    s.plot(slice=slice_, ax=ax, legend=True, drawstyle='steps-post')
    plt.show()
    print(diff)
