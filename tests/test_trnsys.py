import archetypal as ar

def test_trnbuild_from_idf():
    idf_file = r"./input_data/trnbuild/NECB 2011 - Medium Office.idf"

    idfFiles = ar.load_idf(idf_file)
    print(idfFiles)