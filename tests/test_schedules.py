from archetypal import Schedule, load_idf


def test_day_schedule(config):
    """Tests all schedules in the schedule.idf file"""
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)

    for obj in idf['schedules.idf'].idfobjects:
        for bunch in idf['schedules.idf'].idfobjects[obj]:
            try:
                s = Schedule(idf['schedules.idf'], sch_name=bunch.Name,
                             start_day_of_the_week=idf['schedules.idf'].day_of_week_for_start_day)

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

    s = Schedule(idf, sch_name='elecTDVfromCZ06com')

    assert len(s.all_values) == 8760
