__all__ = [
    "DescriptorError",
    "method_descriptor",
    "field_descriptor",
    "split_descriptor"
]

try:
    from collections import namedtuple
except ImportError:
    from .compat.namedtuple import namedtuple

class DescriptorError(Exception):
    """
    Raised when any generic error occurs while parsing a field or method
    descriptor.
    """

def method_descriptor(descriptor):
    if descriptor[0] != "(":
        # A method desciptor must start with its arguments, which are
        # wrapped in brackets.
        raise DescriptorError("no opening bracket")
    
    end = descriptor.find(")")
    if end == -1:
        raise DescriptorError("no terminating bracket")
    
    # Parse the descriptor in two parts, the (optional) method arguments
    # and the mandatory return type.
    args = split_descriptor(descriptor[1:end])
    ret = split_descriptor(descriptor[end + 1:])
    
    # There must always be a return type, even for methods which return
    # nothing (void).
    if not ret:
        raise DescriptorError("no method return type")
    
    return args, ret[0]
    
def field_descriptor(descriptor):
    return split_descriptor(descriptor)[0]
        
def split_descriptor(descriptor):
    """
    Parses a descriptor in a manner compliant with section 4.4.1 of the 
    Java5 ClassFile Format Specification.
    """
    d = descriptor
    i = 0
    ret = []
    post = ""
    while i < len(d):
        # Each "[" denotes another array dimension
        if d[i] == "[":
            post += "[]"
        else:
            # Class types being with a 'L' and are terminated by a ';'.
            if d[i] == "L":
                end = d.find(";", i)
                if end == -1:
                    raise DescriptorError("no terminating semicolon")
                ret.append(d[i + 1:end].replace("/", "."))
                i = end - 1
            elif d[i] == "B":
                ret.append("byte")
            elif d[i] == "C":
                ret.append("char")
            elif d[i] == "D":
                ret.append("double")
            elif d[i] == "F":
                ret.append("float")
            elif d[i] == "I":
                ret.append("int")
            elif d[i] == "J":
                ret.append("long")
            elif d[i] == "S":
                ret.append("short")
            elif d[i] == "Z":
                ret.append("boolean")
            elif d[i] == "V":
                ret.append("void")
            
            if post:
                ret[-1] += post
                post = ""
            
        i += 1
    
    return tuple(ret)

