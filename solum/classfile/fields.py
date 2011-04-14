try:
    from collections import namedtuple
except ImportError:
    from ..compat.namedtuple import namedtuple

from .attributes import AttributeTable
from ..descriptor import field_descriptor

_Field = namedtuple("Field", (
    "flags",
    "name_index",
    "descriptor_index",
    "attributes",
    "name",
    "type_"
))

class Field(_Field):
    pass

class FieldTable(dict):
    def __init__(self, src, constants):
        field_len = src(">H")

        while field_len > 0:
            flags, name_i, desc_i = src(">HHH")
            name = constants[name_i]["value"]
            self[name] = Field(
                flags,
                name_i,
                desc_i,
                AttributeTable(src, constants),
                name,
                field_descriptor(constants[desc_i]["value"])
            )

            field_len -= 1

    def find(self, type_=None):
        """
        Returns all fields that match the given keywords. If no arguments are
        given, return all fields.

        Note: Due to implementation details, the order of fields is not kept.

        Note: Use ifind() for a more efficient version that returns a
              generator.
        """
        if type_:
            return [v for v in self.itervalues() if v.type_ == type_]

        return self.values()

    def ifind(self, type_=None):
        """
        Identical to find, with the exception that it returns a generator
        instead of a list.

        Note: This method cannot be used in concjunction with jar.map() when
              parallel=True, as generators cannot be pickled.
        """
        if not type_:
            return self.itervalues()

        return (v for v in self.itervalues() if v.type_ == type_)

    def find_one(self, name=None, type_=None):
        """
        Returns the first matching field for the given keywords. If no
        arguments are given, return the first found field.

        Note: Due to implementation details, the order of fields is not kept.
        """
        if not name and not type_:
            return self.itervalues().next() if self else None
        elif name and not type_:
            return self.get(name, None)
        elif type_ and not name:
            for v in self.itervalues():
                if v.type_ == type_:
                    return v
        elif type_ and name:
            if name not in self:
                return None

            if self[name].type_ == type_:
                return self[name]

        return None

