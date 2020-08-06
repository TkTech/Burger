from abc import ABC, abstractmethod

from jawa.constants import *
from jawa.util.descriptor import method_descriptor

import six.moves

def class_from_invokedynamic(ins, cf):
    """
    Gets the class type for an invokedynamic instruction that
    calls a constructor.
    """
    const = ins.operands[0]
    bootstrap = cf.bootstrap_methods[const.method_attr_index]
    method = cf.constants.get(bootstrap.method_ref)
    # Make sure this is a reference to LambdaMetafactory
    assert method.reference_kind == 6 # REF_invokeStatic
    assert method.reference.class_.name == "java/lang/invoke/LambdaMetafactory"
    assert method.reference.name_and_type.name == "metafactory"
    assert len(bootstrap.bootstrap_args) == 3 # Num arguments
    # Now check the arguments.  Note that LambdaMetafactory has some
    # arguments automatically filled in.
    methodhandle = cf.constants.get(bootstrap.bootstrap_args[1])
    assert methodhandle.reference_kind == 8 # REF_newInvokeSpecial
    assert methodhandle.reference.name_and_type.name == "<init>"
    # OK, now that we've done all those checks, just get the type
    # from the constructor.
    return methodhandle.reference.class_.name.value

def stringify_invokedynamic(obj, ins, cf):
    """
    Converts an invokedynamic instruction into a string.

    This is a rather limited implementation for now, only handling obj::method.
    """
    const = cf.constants[ins.operands[0].value] # Hack due to packetinstructions not expanding constants
    bootstrap = cf.bootstrap_methods[const.method_attr_index]
    method = cf.constants.get(bootstrap.method_ref)
    # Make sure this is a reference to LambdaMetafactory
    assert method.reference_kind == 6 # REF_invokeStatic
    assert method.reference.class_.name == "java/lang/invoke/LambdaMetafactory"
    assert method.reference.name_and_type.name == "metafactory"
    assert len(bootstrap.bootstrap_args) == 3 # Num arguments
    # Actual implementation.
    methodhandle = cf.constants.get(bootstrap.bootstrap_args[1])
    if methodhandle.reference_kind == 7: # REF_invokeSpecial
        return "%s::%s" % (obj, methodhandle.reference.name_and_type.name.value)
    else:
        raise Exception("Unhandled reference_kind %d" % methodhandle.reference_kind)

def try_eval_lambda(ins, args, cf):
    """
    Attempts to call a lambda function that returns a constant value.
    May throw; this code is very hacky.
    """
    const = ins.operands[0]
    bootstrap = cf.bootstrap_methods[const.method_attr_index]
    method = cf.constants.get(bootstrap.method_ref)
    # Make sure this is a reference to LambdaMetafactory
    assert method.reference_kind == 6 # REF_invokeStatic
    assert method.reference.class_.name == "java/lang/invoke/LambdaMetafactory"
    assert method.reference.name_and_type.name == "metafactory"
    assert len(bootstrap.bootstrap_args) == 3 # Num arguments
    methodhandle = cf.constants.get(bootstrap.bootstrap_args[1])
    assert methodhandle.reference_kind == 6 # REF_invokeStatic
    # We only want to deal with lambdas in the same class
    assert methodhandle.reference.class_.name == cf.this.name

    name2 = methodhandle.reference.name_and_type.name.value
    desc2 = method_descriptor(methodhandle.reference.name_and_type.descriptor.value)

    lambda_method = cf.methods.find_one(name=name2, args=desc2.args_descriptor, returns=desc2.returns_descriptor)
    assert lambda_method

    class Callback(WalkerCallback):
        def on_new(self, ins, const):
            raise Exception("Illegal new")
        def on_invoke(self, ins, const, obj, args):
            raise Exception("Illegal invoke")
        def on_get_field(self, ins, const, obj):
            raise Exception("Illegal getfield")
        def on_put_field(self, ins, const, obj, value):
            raise Exception("Illegal putfield")

    # Set verbose to false because we don't want lots of output if this errors
    # (since it is expected to for more complex methods)
    return walk_method(cf, lambda_method, Callback(), False, args)

class WalkerCallback(ABC):
    """
    Interface for use with walk_method.

    Any of the methods may raise StopIteration to signal the end of checking
    instructions.
    """

    @abstractmethod
    def on_new(self, ins, const):
        """
        Called for a `new` instruction.

        ins: The instruction
        const: The constant, a ConstantClass

        return value: what to put on the stack
        """
        pass

    @abstractmethod
    def on_invoke(self, ins, const, obj, args):
        """
        Called when a method is invoked.

        ins: The instruction
        const: The constant, either a MethodReference or InterfaceMethodRef
        obj: The object being invoked on (or null for a static method)
        args: The arguments to the method, popped from the stack

        return value: what to put on the stack (for a non-void method)
        """
        pass

    @abstractmethod
    def on_get_field(self, ins, const, obj):
        """
        Called for a getfield or getstatic instruction.

        ins: The instruction
        const: The constant, a FieldReference
        obj: The object to get from, or None for a static field

        return value: what to put on the stack
        """
        pass

    @abstractmethod
    def on_put_field(self, ins, const, obj, value):
        """
        Called for a putfield or putstatic instruction.

        ins: The instruction
        const: The constant, a FieldReference
        obj: The object to store into, or None for a static field
        value: The value to assign
        """
        pass

    def on_invokedynamic(self, ins, const, args):
        """
        Called for an invokedynamic instruction.

        ins: The instruction
        const: The constant, a InvokeDynamic
        args: Arguments closed by the created object

        return value: what to put on the stack
        """
        raise Exception("Unexpected invokedynamic: %s" % str(ins))

def walk_method(cf, method, callback, verbose, input_args=None):
    """
    Walks through a method, evaluating instructions and using the callback
    for side-effects.

    The method is assumed to not have any conditionals, and to only return
    at the very end.
    """
    assert isinstance(callback, WalkerCallback)

    stack = []
    locals = {}
    cur_index = 0

    if not method.access_flags.acc_static:
        # TODO: allow specifying this
        locals[cur_index] = object()
        cur_index += 1

    if input_args != None:
        assert len(input_args) == len(method.args)
        for arg in input_args:
            locals[cur_index] = arg
            cur_index += 1
    else:
        for arg in method.args:
            locals[cur_index] = object()
            cur_index += 1

    ins_list = list(method.code.disassemble())
    for ins in ins_list[:-1]:
        if ins in ("bipush", "sipush"):
            stack.append(ins.operands[0].value)
        elif ins.mnemonic.startswith("fconst") or ins.mnemonic.startswith("dconst"):
            stack.append(float(ins.mnemonic[-1]))
        elif ins == "aconst_null":
            stack.append(None)
        elif ins in ("ldc", "ldc_w", "ldc2_w"):
            const = ins.operands[0]

            if isinstance(const, ConstantClass):
                stack.append("%s.class" % const.name.value)
            elif isinstance(const, String):
                stack.append(const.string.value)
            else:
                stack.append(const.value)
        elif ins == "new":
            const = ins.operands[0]

            try:
                stack.append(callback.on_new(ins, const))
            except StopIteration:
                break
        elif ins in ("getfield", "getstatic"):
            const = ins.operands[0]
            if ins.mnemonic != "getstatic":
                obj = stack.pop()
            else:
                obj = None

            try:
                stack.append(callback.on_get_field(ins, const, obj))
            except StopIteration:
                break
        elif ins in ("putfield", "putstatic"):
            const = ins.operands[0]
            value = stack.pop()
            if ins.mnemonic != "putstatic":
                obj = stack.pop()
            else:
                obj = None

            try:
                callback.on_put_field(ins, const, obj, value)
            except StopIteration:
                break
        elif ins in ("invokevirtual", "invokespecial", "invokeinterface", "invokestatic"):
            const = ins.operands[0]
            method_desc = const.name_and_type.descriptor.value
            desc = method_descriptor(method_desc)
            num_args = len(desc.args)

            args = []

            for i in six.moves.range(num_args):
                args.insert(0, stack.pop())
            if ins.mnemonic != "invokestatic":
                obj = stack.pop()
            else:
                obj = None

            try:
                ret = callback.on_invoke(ins, const, obj, args)
            except StopIteration:
                break
            if desc.returns.name != "void":
                stack.append(ret)
        elif ins in ("astore", "istore", "lstore", "fstore", "dstore"):
            locals[ins.operands[0].value] = stack.pop()
        elif ins in ("aload", "iload", "lload", "fload", "dload"):
            stack.append(locals[ins.operands[0].value])
        elif ins == "dup":
            stack.append(stack[-1])
        elif ins == "pop":
            stack.pop()
        elif ins == "anewarray":
            stack.append([None] * stack.pop())
        elif ins == "newarray":
            stack.append([0] * stack.pop())
        elif ins in ("aastore", "bastore", "castore", "sastore", "iastore", "lastore", "fastore", "dastore"):
            value = stack.pop()
            index = stack.pop()
            array = stack.pop()
            if isinstance(array, list) and isinstance(index, int):
                array[index] = value
            elif verbose:
                print("Failed to execute %s: array %s index %s value %s" % (ins, array, index, value))
        elif ins in ("aaload", "baload", "caload", "saload", "iaload", "laload", "faload", "daload"):
            index = stack.pop()
            array = stack.pop()
            if isinstance(array, list) and isinstance(index, int):
                stack.push(array[index])
            elif verbose:
                print("Failed to execute %s: array %s index %s" % (ins, array, index))
        elif ins == "invokedynamic":
            const = ins.operands[0]
            method_desc = const.name_and_type.descriptor.value
            desc = method_descriptor(method_desc)
            num_args = len(desc.args)

            args = []

            for i in six.moves.range(num_args):
                args.insert(0, stack.pop())

            stack.append(callback.on_invokedynamic(ins, ins.operands[0], args))
        elif ins == "checkcast":
            pass
        elif verbose:
            print("Unknown instruction %s: stack is %s" % (ins, stack))

    last_ins = ins_list[-1]
    if last_ins.mnemonic in ("ireturn", "lreturn", "freturn", "dreturn", "areturn"):
        # Non-void method returning
        return stack.pop()
    elif last_ins.mnemonic == "return":
        # Void method returning
        pass
    elif verbose:
        print("Unexpected final instruction %s: stack is %s" % (ins, stack))

def get_enum_constants(cf, verbose):
    # Gets enum constants declared in the given class.
    # Consider the following code:
    """
    public enum TestEnum {
        FOO(900),
        BAR(42) {
            @Override
            public String toString() {
                return "bar";
            }
        },
        BAZ(Integer.getInteger("SomeSystemProperty"));

        public static final TestEnum RECOMMENDED_VALUE = BAR;
        private TestEnum(int i) {}
    }
    """
    # which compiles to:
    """
    public final class TestEnum extends java.lang.Enum<TestEnum>
      minor version: 0
      major version: 52
      flags: ACC_PUBLIC, ACC_FINAL, ACC_SUPER, ACC_ENUM
    {
      public static final TestEnum FOO;
        descriptor: LTestEnum;
        flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL, ACC_ENUM

      public static final TestEnum BAR;
        descriptor: LTestEnum;
        flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL, ACC_ENUM

      public static final TestEnum BAZ;
        descriptor: LTestEnum;
        flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL, ACC_ENUM

      public static final TestEnum RECOMMENDED_VALUE;
        descriptor: LTestEnum;
        flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL

      private static final TestEnum[] $VALUES;
        descriptor: [LTestEnum;
        flags: ACC_PRIVATE, ACC_STATIC, ACC_FINAL, ACC_SYNTHETIC

      public static TestEnum[] values();
        // ...

      public static TestEnum valueOf(java.lang.String);
        // ...

      private TestEnum(int);
        // ...

      static {};
        descriptor: ()V
        flags: ACC_STATIC
        Code:
          stack=5, locals=0, args_size=0
            // Initializing enum constants:
             0: new           #5                  // class TestEnum
             3: dup
             4: ldc           #8                  // String FOO
             6: iconst_0
             7: sipush        900
            10: invokespecial #1                  // Method "<init>":(Ljava/lang/String;II)V
            13: putstatic     #9                  // Field FOO:LTestEnum;
            16: new           #10                 // class TestEnum$1
            19: dup
            20: ldc           #11                 // String BAR
            22: iconst_1
            23: bipush        42
            25: invokespecial #12                 // Method TestEnum$1."<init>":(Ljava/lang/String;II)V
            28: putstatic     #13                 // Field BAR:LTestEnum;
            31: new           #5                  // class TestEnum
            34: dup
            35: ldc           #14                 // String BAZ
            37: iconst_2
            38: ldc           #15                 // String SomeSystemProperty
            40: invokestatic  #16                 // Method java/lang/Integer.getInteger:(Ljava/lang/String;)Ljava/lang/Integer;
            43: invokevirtual #17                 // Method java/lang/Integer.intValue:()I
            46: invokespecial #1                  // Method "<init>":(Ljava/lang/String;II)V
            49: putstatic     #18                 // Field BAZ:LTestEnum;
            // Setting up $VALUES
            52: iconst_3
            53: anewarray     #5                  // class TestEnum
            56: dup
            57: iconst_0
            58: getstatic     #9                  // Field FOO:LTestEnum;
            61: aastore
            62: dup
            63: iconst_1
            64: getstatic     #13                 // Field BAR:LTestEnum;
            67: aastore
            68: dup
            69: iconst_2
            70: getstatic     #18                 // Field BAZ:LTestEnum;
            73: aastore
            74: putstatic     #2                  // Field $VALUES:[LTestEnum;
            // Other user-specified stuff
            77: getstatic     #13                 // Field BAR:LTestEnum;
            80: putstatic     #19                 // Field RECOMMENDED_VALUE:LTestEnum;
            83: return
    }
    """
    # We only care about the enum constants, not other random user stuff
    # (such as RECOMMENDED_VALUE) or the $VALUES thing.  Fortunately,
    # ACC_ENUM helps us with this.  It's worth noting that although MC's
    # obfuscater gets rid of the field names, it does not get rid of the
    # string constant for enum names (which is used by valueOf()), nor
    # does it touch ACC_ENUM.
    # For this method, we don't care about parameters other than the name.
    if not cf.access_flags.acc_enum:
        raise Exception(cf.this.name.value + " is not an enum!")

    enum_fields = list(cf.fields.find(f=lambda field: field.access_flags.acc_enum))
    enum_class = None
    enum_name = None

    result = {}

    for ins in cf.methods.find_one(name="<clinit>").code.disassemble():
        if ins == "new" and enum_class is None:
            const = ins.operands[0]
            enum_class = const.name.value
        elif ins in ("ldc", "ldc_w") and enum_name is None:
            const = ins.operands[0]
            if isinstance(const, String):
                enum_name = const.string.value
        elif ins == "putstatic":
            if enum_class is None or enum_name is None:
                if verbose:
                    print("Ignoring putstatic for %s as enum_class or enum_name is unset" % str(ins))
                continue
            const = ins.operands[0]
            assigned_field = const.name_and_type
            if not any(field.name == assigned_field.name and field.descriptor == assigned_field.descriptor for field in enum_fields):
                # This could happen with an enum constant that sets a field in
                # its constructor, which is unlikely but happens with e.g. this:
                """
                enum Foo {
                    FOO(i = 2);
                    static int i;
                    private Foo(int n) {}
                }
                """
                if verbose:
                    print("Ignoring putstatic for %s as it is to a field not in enum_fields (%s)" % (str(ins), enum_fields))
                continue
            result[enum_name] = {
                'name': enum_name,
                'field': assigned_field.name.value,
                'class': enum_class
            }
            enum_class = None
            enum_name = None

            if len(result) == len(enum_fields):
                break

    if verbose and len(result) != len(enum_fields):
        print("Did not find assignments to all enum fields - fields are %s and result is %s" % (result, enum_fields))

    return result
