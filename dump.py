#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import getopt
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

    # Item superclass
    const = cf.constants.find_one(
       ConstantType.STRING,
       lambda c: "crafting results" in c["string"]["value"]
    )

    if const:
        return ("item_superclass", cf.this)

def packet_ids(jar, name):
    """
    Get all of the packet ID's for each class.
    """
    cf = ClassFile(jar[name], str_as_buffer=True)
    
    ret = {}
    stack = []
    static_init = cf.methods.find_one(name="<clinit>")

    for ins in static_init.instructions:
        # iconst_N (-1 => 5) push N onto the stack
        if ins.name.startswith("iconst"):
            stack.append(int(ins.name[-1]))
        # [bs]ipush push a byte or short (respectively) onto the stack
        elif ins.name.endswith("ipush"):
            stack.append(ins.operands[0][1])
        elif ins.name == "ldc":
            const_i = ins.operands[0][1]
            const = cf.constants[const_i]
            name = const["name"]["value"]

            client = stack.pop()
            server = stack.pop()
            id_ = stack.pop()

            ret[id_] = {
                "id": id_, 
                "class": name,
                "from_client": bool(client), 
                "from_server": bool(server)
            }

    return ret

def notch_lang(contents):
    contents = contents.split("\n")
    for line in contents:
        line = line.strip()
        if not line:
            continue

        tag, value = line.split("=", 1)
        category, name = tag.split(".", 1)

        yield (category, name, value)

def items_pass(jar, name):
    """
    Get as much item information as we can from the constructors
    """
    cf = ClassFile(jar[name], str_as_buffer=True)

    ret = {}
    static_init = cf.methods.find_one(name="<clinit>")

    class_name = None
    name = None
    id_ = None
    field = None

    for ins in static_init.instructions:
        # Note, if we don't have at least 3 static function calls
        # before the next 'new' statement, discard it.
        if ins.name == "new":
            if name and class_name and id_ is not None and field:
                ret[name] = {
                    "class": class_name,
                    "id": id_ + 256,
                    "slug": name,
                    "assigned_to_field": field
                }

            const_i = ins.operands[0][1]
            const = cf.constants[const_i]
            class_name = const["name"]["value"]

            id_ = None
            name = None
            field = None
        elif ins.name.startswith("iconst"):
            if id_ is None:
                id_ = int(ins.name[-1])
        elif ins.name.endswith("ipush"):
            if id_ is None:
                id_ = ins.operands[0][1]
        elif ins.name == "ldc":
            const_i = ins.operands[0][1]
            const = cf.constants[const_i]
            name = const["string"]["value"]
        elif ins.name == "putstatic":
            const_i = ins.operands[0][1]
            const = cf.constants[const_i]
            field_name = const["name_and_type"]["name"]["value"]

            field = field_name

    # Merge the full item names and descriptions
    en_US = jar["lang/en_US.lang"]
    for category, name, value in notch_lang(en_US):
        if category != "item":
            continue

        real_name = name[:-5]
        if real_name not in ret:
            ret[real_name] = {}

        if name.endswith(".desc"):
            ret[real_name]["desc"] = value
        else:
            ret[real_name]["name"] = value

    return ret

def stats_US(jar):
    """
    Get's statistic and achievement name's and description's.
    """
    ret = dict(stat={}, achievement={})
    # Get the contents of the stats language file
    stats_US = jar["lang/stats_US.lang"]
    for category, name, value in notch_lang(stats_US):
        if category == "stat":
            ret["stat"][name] = value
        if category == "achievement":
            real_name = name[:-5] if name.endswith(".desc") else name
            if real_name not in ret["achievement"]:
                ret["achievement"][real_name] = {}
            if name.endswith(".desc"):
                ret["achievement"][real_name]["desc"] = value
            else:
                ret["achievement"][name]["name"] = value

    return ret

def main(argv=None):
    if not argv:
        argv = []

    output = sys.stdout

    try:
        opts, args = getopt.gnu_getopt(argv, "o:", ["output="])
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    for o, a in opts:
        if o in ("-o", "--output"):
            output = open(a, "wb")

    for i,arg in enumerate(args, 1):
        out = {}
        jar = JarFile(arg)

        # The first pass aims to map as much as we can immediately, so we
        # what is where without having to do constant iterations.
        mapped = jar.map(first_pass, parallel=True)
        mapped = filter(lambda f: f, mapped)

        # Get the statistics and achievement text
        out.update(stats_US(jar))

        for type_, name in mapped:
            if type_ == "packet_superclass":
                # Get the packet ID's (if we know where the superclass is)
                out["packets"] = packet_ids(jar, "%s.class" % name)
            elif type_ == "item_superclass":
                # Get the basic item constructors
                out["items"] = items_pass(jar, "%s.class" % name)

        json.dump(out, output, sort_keys=True, indent=4)
        output.write("\n")

    if output is not sys.stdout:
        output.close()

if __name__ == "__main__":
    main(sys.argv[1:])
