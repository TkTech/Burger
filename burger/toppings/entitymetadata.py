import six

from .topping import Topping
from burger.util import WalkerCallback, walk_method

from jawa.constants import *
from jawa.util.descriptor import method_descriptor

class EntityMetadataTopping(Topping):
    PROVIDES = [
        "entities.metadata"
    ]

    DEPENDS = [
        "entities.entity",
        "identify.metadata",
        # For serializers
        "packets.instructions",
        "identify.packet.packetbuffer",
        "identify.blockstate",
        "identify.chatcomponent",
        "identify.itemstack",
        "identify.nbtcompound",
        "identify.particle"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        # This approach works in 1.9 and later; before then metadata was different.
        entities = aggregate["entities"]["entity"]

        datamanager_class = aggregate["classes"]["metadata"]
        datamanager_cf = classloader[datamanager_class]

        create_key_method = datamanager_cf.methods.find_one(f=lambda m: len(m.args) == 2 and m.args[0].name == "java/lang/Class")
        dataparameter_class = create_key_method.returns.name
        dataserializer_class = create_key_method.args[1].name

        register_method = datamanager_cf.methods.find_one(f=lambda m: len(m.args) == 2 and m.args[0].name == dataparameter_class)

        dataserializers_class = None
        for ins in register_method.code.disassemble():
            # The code loops up an ID and throws an exception if it's not registered
            # We want the class that it looks the ID up in
            if ins == "invokestatic":
                const = ins.operands[0]
                dataserializers_class = const.class_.name.value
            elif dataserializers_class and ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if const == "Unregistered serializer ":
                    break
        else:
            raise Exception("Failed to identify dataserializers")

        base_entity_class = entities["~abstract_entity"]["class"]
        base_entity_cf = classloader[base_entity_class]
        register_data_method_name = None
        register_data_method_desc = "()V"
        # The last call in the base entity constructor is to registerData() (formerly entityInit())
        for ins in base_entity_cf.methods.find_one(name="<init>").code.disassemble():
            if ins.mnemonic == "invokevirtual":
                const = ins.operands[0]
                if const.name_and_type.descriptor == register_data_method_desc:
                    register_data_method_name = const.name_and_type.name.value
                    # Keep looping, to find the last call

        dataserializers = EntityMetadataTopping.identify_serializers(classloader, dataserializer_class, dataserializers_class, aggregate["classes"], verbose)
        aggregate["entities"]["dataserializers"] = dataserializers
        dataserializers_by_field = {serializer["field"]: serializer for serializer in six.itervalues(dataserializers)}

        entity_classes = {e["class"]: e["name"] for e in six.itervalues(entities)}
        parent_by_class = {}
        metadata_by_class = {}
        bitfields_by_class = {}

        # this flag is shared among all entities
        # getSharedFlag is currently the only method in Entity with those specific args and returns, this may change in the future! (hopefully not)
        shared_get_flag_method = base_entity_cf.methods.find_one(args="I", returns="Z").name.value

        def fill_class(cls):
            # Returns the starting index for metadata in subclasses of cls
            if cls == "java/lang/Object":
                return 0
            if cls in metadata_by_class:
                return len(metadata_by_class[cls]) + fill_class(parent_by_class[cls])

            cf = classloader[cls]
            super = cf.super_.name.value
            parent_by_class[cls] = super
            index = fill_class(super)

            metadata = []
            class MetadataFieldContext(WalkerCallback):
                def __init__(self):
                    self.cur_index = index

                def on_invoke(self, ins, const, obj, args):
                    if const.class_.name == datamanager_class and const.name_and_type.name == create_key_method.name and const.name_and_type.descriptor == create_key_method.descriptor:
                        # Call to createKey.
                        # Sanity check: entities should only register metadata for themselves
                        if args[0] != cls + ".class":
                            # ... but in some versions, mojang messed this up with potions... hence why the sanity check exists in vanilla now.
                            if verbose:
                                other_class = args[0][:-len(".class")]
                                name = entity_classes.get(cls, "Unknown")
                                other_name = entity_classes.get(other_class, "Unknown")
                                print("An entity tried to register metadata for another entity: %s (%s) from %s (%s)" % (other_name, other_class, name, cls))

                        serializer = args[1]
                        index = self.cur_index
                        self.cur_index += 1

                        metadata_entry = {
                            "serializer_id": serializer["id"],
                            "serializer": serializer["name"] if "name" in serializer else serializer["id"],
                            "index": index
                        }
                        metadata.append(metadata_entry)
                        return metadata_entry

                def on_put_field(self, ins, const, obj, value):
                    if isinstance(value, dict):
                        value["field"] = const.name_and_type.name.value

                def on_get_field(self, ins, const, obj):
                    if const.class_.name == dataserializers_class:
                        return dataserializers_by_field[const.name_and_type.name.value]

                def on_invokedynamic(self, ins, const, args):
                    return object()

                def on_new(self, ins, const):
                    return object()

            init = cf.methods.find_one(name="<clinit>")
            if init:
                ctx = MetadataFieldContext()
                walk_method(cf, init, ctx, verbose)
                index = ctx.cur_index

            class MetadataDefaultsContext(WalkerCallback):
                def __init__(self, wait_for_putfield=False):
                    self.textcomponentstring = None
                    # True whlie waiting for "this.dataManager = new EntityDataManager(this);" when going through the entity constructor
                    self.waiting_for_putfield = wait_for_putfield

                def on_invoke(self, ins, const, obj, args):
                    if self.waiting_for_putfield:
                        return

                    if "Optional" in const.class_.name.value:
                        if const.name_and_type.name in ("absent", "empty"):
                            return "Empty"
                        elif len(args) == 1:
                            # Assume "of" or similar
                            return args[0]
                    elif const.name_and_type.name == "valueOf":
                        # Boxing methods
                        if const.class_.name == "java/lang/Boolean":
                            return bool(args[0])
                        else:
                            return args[0]
                    elif const.name_and_type.name == "<init>":
                        if const.class_.name == self.textcomponentstring:
                            obj["text"] = args[0]

                        return
                    elif const.class_.name == datamanager_class:
                        assert const.name_and_type.name == register_method.name
                        assert const.name_and_type.descriptor == register_method.descriptor

                        # args[0] is the metadata entry, and args[1] is the default value
                        if args[0] is not None and args[1] is not None:
                            args[0]["default"] = args[1]

                        return
                    elif const.name_and_type.descriptor.value.endswith("L" + datamanager_class + ";"):
                        # getDataManager, which doesn't really have a reason to exist given that the data manager field is accessible
                        return None
                    elif const.name_and_type.name == register_data_method_name and const.name_and_type.descriptor == register_data_method_desc:
                        # Call to super.registerData()
                        return

                def on_put_field(self, ins, const, obj, value):
                    if const.name_and_type.descriptor == "L" + datamanager_class + ";":
                        if not self.waiting_for_putfield:
                            raise Exception("Unexpected putfield: %s" % (ins,))
                        self.waiting_for_putfield = False

                def on_get_field(self, ins, const, obj):
                    if self.waiting_for_putfield:
                        return

                    if const.name_and_type.descriptor == "L" + dataparameter_class + ";":
                        # Definitely shouldn't be registering something declared elsewhere
                        assert const.class_.name == cls
                        for metadata_entry in metadata:
                            if const.name_and_type.name == metadata_entry.get("field"):
                                return metadata_entry
                        else:
                            if verbose:
                                print("Can't figure out metadata entry for field %s; default will not be set." % (const,))
                            return None

                    if const.class_.name == aggregate["classes"]["position"]:
                        # Assume BlockPos.ORIGIN
                        return "(0, 0, 0)"
                    elif const.class_.name == aggregate["classes"]["itemstack"]:
                        # Assume ItemStack.EMPTY
                        return "Empty"
                    elif const.name_and_type.descriptor == "L" + datamanager_class + ";":
                        return
                    else:
                        return None

                def on_new(self, ins, const):
                    if self.waiting_for_putfield:
                        return

                    if self.textcomponentstring == None:
                        # Check if this is TextComponentString
                        temp_cf = classloader[const.name.value]
                        for str in temp_cf.constants.find(type_=String):
                            if "TextComponent{text=" in str.string.value:
                                self.textcomponentstring = const.name.value
                                break

                    if const.name == aggregate["classes"]["nbtcompound"]:
                        return "Empty"
                    elif const.name == self.textcomponentstring:
                        return {'text': None}

            register = cf.methods.find_one(name=register_data_method_name, f=lambda m: m.descriptor == register_data_method_desc)
            if register and not register.access_flags.acc_abstract:
                walk_method(cf, register, MetadataDefaultsContext(), verbose)
            elif cls == base_entity_class:
                walk_method(cf, cf.methods.find_one(name="<init>"), MetadataDefaultsContext(True), verbose)

            get_flag_method = None

            # find if the class has a `boolean getFlag(int)` method
            for method in cf.methods.find(args="I", returns="Z"):
                previous_operators = []
                for ins in method.code.disassemble():
                    if ins.mnemonic == "bipush":
                        # check for a series of operators that looks something like this
                        # `return ((Byte)this.R.a(bo) & var1) != 0;`
                        operator_matcher = ["aload", "getfield", "getstatic", "invokevirtual", "checkcast", "invokevirtual", "iload", "iand", "ifeq", "bipush", "goto"]
                        previous_operators_match = previous_operators == operator_matcher

                        if previous_operators_match and ins.operands[0].value == 0:
                            # store the method name as the result for later
                            get_flag_method = method.name.value

                    previous_operators.append(ins.mnemonic)

            bitfields = []

            # find the methods that get bit fields
            for method in cf.methods.find(args="", returns="Z"):
                if method.code:
                    bitmask_value = None
                    stack = []
                    for ins in method.code.disassemble():
                        # the method calls getField() or getSharedField()
                        if ins.mnemonic in ("invokevirtual", "invokespecial", "invokeinterface", "invokestatic"):
                            calling_method = ins.operands[0].name_and_type.name.value

                            has_correct_arguments = ins.operands[0].name_and_type.descriptor.value == "(I)Z"

                            is_getflag_method = has_correct_arguments and calling_method == get_flag_method
                            is_shared_getflag_method = has_correct_arguments and calling_method == shared_get_flag_method

                            # if it's a shared flag, update the bitfields_by_class for abstract_entity
                            if is_shared_getflag_method and stack:
                                bitmask_value = stack.pop()
                                if bitmask_value is not None:
                                    base_entity_cls = base_entity_cf.this.name.value
                                    if base_entity_cls not in bitfields_by_class:
                                        bitfields_by_class[base_entity_cls] = []
                                    bitfields_by_class[base_entity_cls].append({
                                        # we include the class here so it can be easily figured out from the mappings
                                        "class": cls,
                                        "method": method.name.value,
                                        "mask": 1 << bitmask_value
                                    })
                                bitmask_value = None
                            elif is_getflag_method and stack:
                                bitmask_value = stack.pop()
                                break
                        elif ins.mnemonic == "iand":
                            # get the last item in the stack, since it's the bitmask
                            bitmask_value = stack[-1]
                            break
                        elif ins.mnemonic == "bipush":
                            stack.append(ins.operands[0].value)
                    if bitmask_value:
                        bitfields.append({
                            "method": method.name.value,
                            "mask": bitmask_value
                        })


            metadata_by_class[cls] = metadata
            if cls not in bitfields_by_class:
                bitfields_by_class[cls] = bitfields
            else:
                bitfields_by_class[cls].extend(bitfields)
            return index

        for cls in six.iterkeys(entity_classes):
            fill_class(cls)

        for e in six.itervalues(entities):
            cls = e["class"]
            metadata = e["metadata"] = []

            if metadata_by_class[cls]:
                metadata.append({
                    "class": cls,
                    "data": metadata_by_class[cls],
                    "bitfields": bitfields_by_class[cls]
                })

            cls = parent_by_class[cls]
            while cls not in entity_classes and cls != "java/lang/Object" :
                # Add metadata from _abstract_ parent classes, at the start
                if metadata_by_class[cls]:
                    metadata.insert(0, {
                        "class": cls,
                        "data": metadata_by_class[cls],
                        "bitfields": bitfields_by_class[cls]
                    })
                cls = parent_by_class[cls]

            # And then, add a marker for the concrete parent class.
            if cls in entity_classes:
                # Always do this, even if the immediate concrete parent has no metadata
                metadata.insert(0, {
                    "class": cls,
                    "entity": entity_classes[cls]
                })

    @staticmethod
    def identify_serializers(classloader, dataserializer_class, dataserializers_class, classes, verbose):
        serializers_by_field = {}
        serializers = {}
        id = 0
        dataserializers_cf = classloader[dataserializers_class]
        for ins in dataserializers_cf.methods.find_one(name="<clinit>").code.disassemble():
            #print(ins, serializers_by_field, serializers)
            # Setting up the serializers
            if ins.mnemonic == "new":
                const = ins.operands[0]
                last_cls = const.name.value
            elif ins.mnemonic == "putstatic":
                const = ins.operands[0]
                if const.name_and_type.descriptor.value != "L" + dataserializer_class + ";":
                    # E.g. setting the registry.
                    continue

                field = const.name_and_type.name.value
                serializer = EntityMetadataTopping.identify_serializer(classloader, last_cls, classes, verbose)

                serializer["class"] = last_cls
                serializer["field"] = field

                serializers_by_field[field] = serializer
            # Actually registering them
            elif ins.mnemonic == "getstatic":
                const = ins.operands[0]
                field = const.name_and_type.name.value

                serializer = serializers_by_field[field]
                serializer["id"] = id
                name = serializer.get("name") or str(id)
                if name not in serializers:
                    serializers[name] = serializer
                else:
                    if verbose:
                        print("Duplicate serializer with identified name %s: original %s, new %s" % (name, serializers[name], serializer))
                    serializers[str(id)] = serializer # This hopefully will not clash but still shouldn't happen in the first place

                id += 1

        return serializers

    @staticmethod
    def identify_serializer(classloader, cls, classes, verbose):
        # In here because otherwise the import messes with finding the topping in this file
        from .packetinstructions import PacketInstructionsTopping as _PIT
        from .packetinstructions import PACKETBUF_NAME

        cf = classloader[cls]
        sig = cf.attributes.find_one(name="Signature").signature.value
        # Input:
        # Ljava/lang/Object;Los<Ljava/util/Optional<Lel;>;>;
        # First, get the generic part only:
        # Ljava/util/Optional<Lel;>;
        # Then, get rid of the 'L' and ';' by removing the first and last chars
        # java/util/Optional<Lel;>
        # End result is still a bit awful, but it can be worked with...
        inner_type = sig[sig.index("<") + 1 : sig.rindex(">")][1:-1]
        serializer = {
            "type": inner_type
        }

        # Try to do some recognition of what it is:
        name = None
        name_prefix = ""
        if "Optional<" in inner_type:
            # NOTE: both java and guava optionals are used at different times
            name_prefix = "Opt"
            # Get rid of another parameter
            inner_type = inner_type[inner_type.index("<") + 1 : inner_type.rindex(">")][1:-1]

        if inner_type.startswith("java/lang/"):
            name = inner_type[len("java/lang/"):]
            if name == "Integer":
                name = "VarInt"
        elif inner_type == "java/util/UUID":
            name = "UUID"
        elif inner_type == "java/util/OptionalInt":
            name = "OptVarInt"
        elif inner_type == classes["nbtcompound"]:
            name = "NBT"
        elif inner_type == classes["itemstack"]:
            name = "Slot"
        elif inner_type == classes["chatcomponent"]:
            name = "Chat"
        elif inner_type == classes["position"]:
            name = "BlockPos"
        elif inner_type == classes["blockstate"]:
            name = "BlockState"
        elif inner_type == classes.get("particle"): # doesn't exist in all versions
            name = "Particle"
        else:
            # Try some more tests, based on the class itself:
            try:
                content_cf = classloader[inner_type]
                if len(list(content_cf.fields.find(type_="F"))) == 3:
                    name = "Rotations"
                elif content_cf.constants.find_one(type_=String, f=lambda c: c == "down"):
                    name = "Facing"
                elif content_cf.constants.find_one(type_=String, f=lambda c: c == "FALL_FLYING"):
                    assert content_cf.access_flags.acc_enum
                    name = "Pose"
                elif content_cf.constants.find_one(type_=String, f=lambda c: c == "profession"):
                    name = "VillagerData"
            except:
                if verbose:
                    print("Failed to determine name of metadata content type %s" % inner_type)
                    import traceback
                    traceback.print_exc()

        if name:
            serializer["name"] = name_prefix + name

        # Decompile the serialization code.
        # Note that we are using the bridge method that takes an object, and not the more find
        try:
            write_args = "L" + classes["packet.packetbuffer"] + ";Ljava/lang/Object;"
            methods = list(cf.methods.find(returns="V", args=write_args))
            assert len(methods) == 1
            operations = _PIT.operations(classloader, cf, classes, verbose,
                    methods[0], arg_names=("this", PACKETBUF_NAME, "value"))
            serializer.update(_PIT.format(operations))
        except:
            if verbose:
                print("Failed to process operations for metadata serializer", serializer)
                import traceback
                traceback.print_exc()

        return serializer
