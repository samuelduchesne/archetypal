import archetypal as ar


@ar.idfclass.register_idf_function("calibrate")
class Calibrator:
    def __init__(self, idf_obj):
        self._validate(idf_obj)
        self._obj = idf_obj

    @staticmethod
    def _validate(obj):
        # Optional, verify that some conditions are respected before the calibrate
        # module can be used.
        if "condition" not in obj:
            raise AttributeError("Condition must be respected to use calibrator")

    @property
    def a_property(self):
        """some other property that can returned by the calibrate method

        Examples:
            >>> idf = ar.IDF()
            >>> idf.calibrate.a_property

        """
        # return a property of the class
        return None

    def a_function(self, args):
        """some other function that can be used on the calibrate method.

        Examples:
            >>> idf = ar.IDF()
            >>> args = set() # args of apply_function method
            >>> idf.calibrate.a_function(*args)

        """
        pass
