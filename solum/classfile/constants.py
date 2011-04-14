class ConstantTypes(object):
    CLASS = 7
    FIELD_REF = 9
    METHOD_REF = 10
    INTERFACE_METHOD_REF = 11
    REFERENCE = (9, 10, 11)
    STRING = 8
    INTEGER = 3
    INT = 3
    FLOAT = 4
    LONG = 5
    DOUBLE = 6
    NAME_AND_TYPE = 12
    UTF8 = 1

class ConstantPool(dict):
    def find(self, tag=None, f=None):
        ret = []
        for v in self.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            ret.append(v)

        return ret

    def find_one(self, tag=None, f=None):
        for v in self.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            return v
