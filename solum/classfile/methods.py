try:
    from collections import namedtuple
except ImportError:
    from ..compat.namedtuple import namedtuple

from .attributes import AttributeTable
from ..descriptor import method_descriptor

_Method = namedtuple("Method", (
    "flags",
    "name_index",
    "descriptor_index",
    "attributes",
    "name",
    "returns",
    "args"
))

class Method(_Method):
    pass

class MethodTable(list):
    def __init__(self, src, constants):
        method_len = src(">H")

        while method_len > 0:
            flags, name_i, desc_i = src(">HHH")
            name = constants[name_i]["value"]
            desc = method_descriptor(constants[desc_i]["value"])

            self.append(Method(
                flags,
                name_i,
                desc_i,
                AttributeTable(src, constants),
                name,
                desc[1],
                desc[0]
            ))

            method_len -= 1

    def find(self, name=None, args=None, returns=None):
        tmp = []
        for method in self:
            if name and name != method.name:
                continue
            if args and args != method.args:
                continue
            if returns and returns != method.returns:
                continue
            
            tmp.append(method)

        return tmp

    def find_one(self, name=None, args=None, returns=None):
        for method in self:
            if name and name != method.name:
                continue
            if args and args != method.args:
                continue
            if returns and returns != method.returns:
                continue

            return method

        return None
