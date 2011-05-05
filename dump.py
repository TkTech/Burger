#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import getopt
import pprint

from solum import JarFile, ClassFile, ConstantType

VERBOSE = False
OUTPUT = sys.stdout

def first_pass(buff):
    """
    The first pass across the JAR will identify all possible classes it
    can, maping them by the 'type' it implements.

    We have limited information available to us on this pass. We can only
    check for known signatures and predictable constants. In the next pass,
    we'll have the initial mapping from this pass available to us.
    """
    # str_as_buffer is required, else it'll treat the string buffer
    # as a file path.
    cf = ClassFile(buff, str_as_buffer=True)

    # First up, finding the "block superclass" (as we'll call it).
    # We'll look for one of the debugging messages.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "when adding" in c["string"]["value"]
    )

    if const:
        # We've found the block superclass, all done.
        return ("block_superclass", cf.this)

    # Next up, see if we've got the packet superclass in the same way.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "Duplicate packet" in c["string"]["value"]
    )

    if const:
        # We've found the packet superclass.
        return ("packet_superclass", cf.this)


def main(argv=None):
    if not argv:
        argv = []

    try:
        opts, args = getopt.getopt(argv, "ho:v", ["help", "output="])
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    for arg in args:
        jar = JarFile(arg)
        mapped = jar.map(first_pass, parallel=True)
        mapped = filter(lambda f: f, mapped)
        pprint.pprint(mapped)

if __name__ == "__main__":
    main(sys.argv[1:])
