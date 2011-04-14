try:
    from collections import namedtuple
except ImportError:
    from ..compat.namedtuple import namedtuple

import struct
    
_Attribute = namedtuple("Attribute", (
    "name_index",
    "name",
    "data"
))

class Attribute(object):
    def __init__(self, constants, name_index, name, data):
        self.name_index = name_index,
        self.name = name
        self.data = data

        if hasattr(self, "parse"):
            self._pos = 0
            def src(format):
                length = struct.calcsize(format)
                tmp = struct.unpack_from(format, self.data, self._pos)
                self._pos += length
                return tmp[0] if len(tmp) == 1 else tmp

            self.parse(src, constants)

# Used by the CodeAttribute to represent exception ranges
CodeException = namedtuple("CodeException", [
    "start_pc",
    "end_pc",
    "handler_pc",
    "catch_type"
])

class CodeAttribute(Attribute):
    def parse(self, src, constants):
        self.max_stack, self.max_locals, code_len = src(">HHI")
        self.code, exp_len = src(">%ssH" % code_len)

        self.exceptions = []
        while exp_len > 0:
            self.exceptions.append(CodeException(*src(">HHHH")))
            exp_len -= 1

        self.attributes = AttributeTable(src, constants)

    def __repr__(self):
        f = "Code(max_stack=%r, max_locals=%r, code=..., exceptions=%r)"
        return f % (self.max_stack, self.max_locals, self.exceptions)

_attributes = {
    "Code": CodeAttribute
}

class AttributeTable(list):
    def __init__(self, src, constants):
        attrib_len = src(">H")

        while attrib_len > 0:
            name_i, length = src(">HI")
            data = src(">%ss" % length)
            name = constants[name_i]["value"]

            self.append(_attributes.get(name, Attribute)(
                constants,
                name_i,
                constants[name_i]["value"],
                data
            ))
            attrib_len -= 1

    def find(self, name=None):
        """
        Returns all methods that match the given keywords. If no arguments are
        given, return all methods. The order of the returned list is the same
        as the order on disk.

        Note: Use ifind() for a more efficient version that returns a
              generator.
        """
        if name:
            return [a for a in self if a.name == name]

        return list(self)

    def ifind(self, name=None):
        """
        Identical to find, with the exception that it returns a generator
        instead of a list.

        Note: This method cannot be used in concjunction with jar.map() when
              parallel=True, as generators cannot be pickled.
        """
        if name:
            return (a for a in self if a.name == name)

        return (a for a in self)

    def find_one(self):
        pass
