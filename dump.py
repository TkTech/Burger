#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import getopt
import pprint
import json

from solum import JarFile, ClassFile, ConstantType

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

    # The individual packet classes have a unique signature.
    pread = cf.methods.find_one(args=("java.io.DataInputStream",))
    pwrite = cf.methods.find_one(args=("java.io.DataOutputStream",))
    size = cf.methods.find_one(returns="int", args=())

    if pread and pwrite and size:
        return ("packet", cf.this)

    # The main recipe superclass.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "X#X" in c["string"]["value"]
    )

    if const:
        return ("recipe_superclass", cf.this)

    # First of 2 auxilary recipe classes. Appears to be items with
    # inventory, + sandstone.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: c["string"]["value"] == "# #"
    )

    if const:
        return ("recipe_inventory", cf.this)

    # Second auxilary recipe class. Appears to be coloured cloth?
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: c["string"]["value"] == "###"
    )

    if const:
        return ("recipe_cloth", cf.this)

def main(argv=None):
    if not argv:
        argv = []

    verbose = False
    output = sys.stdout

    try:
        opts, args = getopt.gnu_getopt(argv, "o:v", ["output="])
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    for o, a in opts:
        if o == "-v":
            verbose = True
        elif o in ("-o", "--output"):
            output = open(a, "wb")

    for i,arg in enumerate(args, 1):
        if verbose:
            print u"\u2192 Opening %s (%s/%s)..." % (arg, i, len(args))

        jar = JarFile(arg)
        mapped = jar.map(first_pass, parallel=True)
        mapped = filter(lambda f: f, mapped)

        if verbose:
            print u"  \u21b3 %s matche(s) on first pass" % (len(mapped))

        out = {
            "class_map": mapped
        }
        json.dump(out, output, sort_keys=True, indent=4)
        output.write("\n")

    if output is not sys.stdout:
        output.close()

if __name__ == "__main__":
    main(sys.argv[1:])
