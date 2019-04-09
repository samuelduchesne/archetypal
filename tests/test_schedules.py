from archetypal import Schedule, load_idf


def test_day_schedule(config):
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)

    for obj in idf['schedules.idf'].idfobjects:
        for bunch in idf['schedules.idf'].idfobjects[obj]:
            try:
                s = Schedule(idf['schedules.idf'], schName=bunch.Name,
                             startDayOfTheWeek=0)

                values = s.getScheduleValues()
                print(values)
            except:
                pass


def test_file_schedule(config):
    idf_file = './input_data/schedules/schedules.idf'
    idf = load_idf(idf_file)['schedules.idf']

    s = Schedule(idf, schName='elecTDVfromCZ06com')

    assert len(s.all_values) == 8760
