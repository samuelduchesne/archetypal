from archetypal import Schedule, load_idf


def test_day_schedule(config):
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)

    for obj in idf['schedules.idf'].idfobjects:
        for bunch in idf['schedules.idf'].idfobjects[obj]:
            try:
                s = Schedule(idf['schedules.idf'], sch_name=bunch.Name,
                             start_day_of_the_week=0)

                values = s.get_schedule_values()
                print(values)
            except:
                pass


def test_file_schedule(config):
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, sch_name='elecTDVfromCZ06com')

    assert len(s.all_values) == 8760
