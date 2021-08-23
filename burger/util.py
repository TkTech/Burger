from abc import ABC, abstractmethod

from jawa.assemble import assemble
from jawa.cf import ClassFile
from jawa.methods import Method
from jawa.constants import *
from jawa.util.descriptor import method_descriptor
from jawa.util.bytecode import Operand

import six.moves

# See https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-4.html#jvms-4.4.8
REF_getField = 1
REF_getStatic = 2
REF_putField = 3
REF_putStatic = 4
REF_invokeVirtual = 5
REF_invokeStatic = 6
REF_invokeSpecial = 7
REF_newInvokeSpecial = 8
REF_invokeInterface = 9

FIELD_REFS = (REF_getField, REF_getStatic, REF_putField, REF_putStatic)

class InvokeDynamicInfo(ABC):
    @staticmethod
    def create(ins, cf):
        if isinstance(ins.operands[0], Operand):
            # Hack due to packetinstructions not expanding constants
            const = cf.constants[ins.operands[0].value]
        else:
            const = ins.operands[0]

        bootstrap = cf.bootstrap_methods[const.method_attr_index]
        method = cf.constants.get(bootstrap.method_ref)
        if method.reference.class_.name == "java/lang/invoke/LambdaMetafactory":
            return LambdaInvokeDynamicInfo(ins, cf, const)
        elif method.reference.class_.name == "java/lang/invoke/StringConcatFactory":
            return StringConcatInvokeDynamicInfo(ins, cf, const)
        else:
            raise Exception("Unknown invokedynamic class: " + method.reference.class_.name.value)

    def __init__(self, ins, cf, const):
        self._ins = ins
        self._cf = cf
        self.stored_args = None

    @abstractmethod
    def __str__():
        pass

    def apply_to_stack(self, stack):
        """
        Used to simulate an invokedynamic instruction.  Pops relevant args, and
        puts this object (used to simulate the function we return) onto the stack.
        """
        assert self.stored_args == None # Should only be called once

        num_arguments = len(self.dynamic_desc.args)
        if num_arguments > 0:
            self.stored_args = stack[-len(self.dynamic_desc.args):]
        else:
            self.stored_args = []
        for _ in six.moves.range(num_arguments):
            stack.pop()

        stack.append(self)

    @abstractmethod
    def create_method(self):
        pass

class LambdaInvokeDynamicInfo(InvokeDynamicInfo):
    """
    Stores information related to an invokedynamic instruction.
    """

    def __init__(self, ins, cf, const):
        super().__init__(ins, cf, const)
        self.generated_cf = None
        self.generated_method = None

        bootstrap = cf.bootstrap_methods[const.method_attr_index]
        method = cf.constants.get(bootstrap.method_ref)
        # Make sure this is a reference to LambdaMetafactory.metafactory
        assert method.reference_kind == REF_invokeStatic
        assert method.reference.class_.name == "java/lang/invoke/LambdaMetafactory"
        assert method.reference.name_and_type.name == "metafactory"
        assert len(bootstrap.bootstrap_args) == 3 # Num arguments
        # It could also be a reference to LambdaMetafactory.altMetafactory.
        # This is used for intersection types, which I don't think I've ever seen
        # used in the wild, and maybe for some other things.  Here's an example:
        """
        class Example {
            interface A { default int foo() { return 1; } }
            interface B { int bar(); }
            public Object test() {
                return (A & B)() -> 1;
            }
        }
        """
        # See https://docs.oracle.com/javase/specs/jls/se8/html/jls-4.html#jls-4.9
        # and https://docs.oracle.com/javase/specs/jls/se8/html/jls-9.html#jls-9.8-200-D
        # for details.  Minecraft doesn't use this, so let's just pretend it doesn't exist.

        # Now check the arguments.  Note that LambdaMetafactory has some
        # arguments automatically filled in.  The bootstrap arguments are:
        # args[0] is samMethodType, signature of the implemented method
        # args[1] is implMethod, the method handle that is used
        # args[2] is instantiatedMethodType, narrower signature of the implemented method
        # We only really care about the method handle, and just assume that the
        # method handle satisfies instantiatedMethodType, and that that also
        # satisfies samMethodType.  instantiatedMethodType could maybe be used
        # to get the type of object created by the returned function, but I'm not
        # sure if there's a reason to do that over just looking at the handle.
        methodhandle = cf.constants.get(bootstrap.bootstrap_args[1])
        self.ref_kind = methodhandle.reference_kind

        # instantiatedMethodType does have a use when executing the created
        # object, so store it for later.
        instantiated = cf.constants.get(bootstrap.bootstrap_args[2])
        self.instantiated_desc = method_descriptor(instantiated.descriptor.value)

        assert self.ref_kind >= REF_getField and self.ref_kind <= REF_invokeInterface
        # Javac does not appear to use REF_getField, REF_getStatic,
        # REF_putField, or REF_putStatic, so don't bother handling fields here.
        assert self.ref_kind not in FIELD_REFS

        self.method_class = methodhandle.reference.class_.name.value
        self.method_name = methodhandle.reference.name_and_type.name.value
        self.method_desc = method_descriptor(methodhandle.reference.name_and_type.descriptor.value)

        if self.ref_kind == REF_newInvokeSpecial:
            # https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-4.html#jvms-4.4.8-200-C.2
            assert self.method_name == "<init>"
        else:
            # https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-4.html#jvms-4.4.8-200-C.1
            assert self.method_name not in ("<init>", "<clinit>")

        # Although invokeinterface won't cause problems here, other code likely
        # will break with it, so bail out early for now (if it's eventually used,
        # it can be fixed later)
        assert self.ref_kind != REF_invokeInterface

        # As for stack changes, consider the following:
        """
        public Supplier<String> foo() {
          return this::toString;
        }
        public Function<Object, String> bar() {
          return Object::toString;
        }
        public static Supplier<String> baz(String a, String b, String c) {
          return () -> a + b + c;
        }
        public Supplier<Object> quux() {
          return Object::new;
        }
        """
        # Which disassembles (tidied to remove java.lang and java.util) to:
        """
        Constant pool:
          #2 = InvokeDynamic      #0:#38         // #0:get:(LClassName;)LSupplier;
          #3 = InvokeDynamic      #1:#41         // #1:apply:()LFunction;
          #4 = InvokeDynamic      #2:#43         // #2:get:(LString;LString;LString;)LSupplier;
          #5 = InvokeDynamic      #3:#45         // #3:get:()LSupplier;
        public Supplier<String> foo();
          Code:
            0: aload_0
            1: invokedynamic #2,  0
            6: areturn
        public Function<Object, String> bar();
          Code:
            0: invokedynamic #3,  0
            5: areturn
        public static Supplier<String> baz(String, String, String);
          Code:
            0: aload_0
            1: aload_1
            2: aload_2
            3: invokedynamic #4,  0
            8: areturn
        public Supplier<java.lang.Object> quux();
          Code:
            0: invokedynamic #5,  0
            5: areturn
        private static synthetic String lambda$baz$0(String, String, String);
          -snip-
        BootstrapMethods:
          0: #34 invokestatic -snip- LambdaMetafactory.metafactory -snip-
            Method arguments:
              #35 ()LObject;
              #36 invokevirtual Object.toString:()LString;
              #37 ()LString;
          1: #34 invokestatic -snip- LambdaMetafactory.metafactory -snip-
            Method arguments:
              #39 (LObject;)LObject;
              #36 invokevirtual Object.toString:()LString;
              #40 (LObject;)LString;
          2: #34 invokestatic -snip- LambdaMetafactory.metafactory -snip-
            Method arguments:
              #35 ()LObject;
              #42 invokestatic ClassName.lambda$baz$0:(LString;LString;LString;)LString;
              #37 ()LString;
          3: #34 invokestatic -snip- LambdaMetafactory.metafactory -snip-
            Method arguments:
              #35 ()LObject;
              #44 newinvokespecial Object."<init>":()V
              #35 ()LObject;
        """
        # Note that both foo and bar have invokevirtual in the method handle,
        # but `this` is added to the stack in foo().
        # Similarly, baz pushes 3 arguments to the stack.  Unfortunately the JVM
        # spec doesn't make it super clear how to decide how many items to
        # pop from the stack for invokedynamic.  My guess, looking at the
        # constant pool, is that it's the name_and_type member of InvokeDynamic,
        # specifically the descriptor, that determines stack changes.
        # https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-4.html#jvms-4.10.1.9.invokedynamic
        # kinda confirms this without explicitly stating it.
        self.dynamic_name = const.name_and_type.name.value
        self.dynamic_desc = method_descriptor(const.name_and_type.descriptor.value)

        assert self.dynamic_desc.returns.name != "void"
        self.implemented_iface = self.dynamic_desc.returns.name

        # created_type is the type returned by the function we return.
        if self.ref_kind == REF_newInvokeSpecial:
            self.created_type = self.method_class
        else:
            self.created_type = self.method_desc.returns.name

    def __str__(self):
        # TODO: be closer to Java syntax (using the stored args)
        return "%s::%s" % (self.method_class, self.method_name)

    def create_method(self):
        """
        Creates a Method that corresponds to the generated function call.
        It will be part of a class that implements the right interface, and will
        have the appropriate name and signature.
        """
        assert self.stored_args != None
        if self.generated_method != None:
            return (self.generated_cf, self.generated_method)

        class_name = self._cf.this.name.value + "_lambda_" + str(self._ins.pos)
        self.generated_cf = ClassFile.create(class_name)
        # Jawa doesn't seem to expose this cleanly.  Technically we don't need
        # to implement the interface because the caller doesn't actually care,
        # but it's better to implement it anyways for the future.
        # (Due to the hacks below, the interface isn't even implemented properly
        # since the method we create has additional parameters and is static.)
        iface_const = self.generated_cf.constants.create_class(self.implemented_iface)
        self.generated_cf._interfaces.append(iface_const.index)

        # HACK: This officially should use instantiated_desc.descriptor,
        # but instead use a combination of the stored arguments and the
        # instantiated descriptor to make packetinstructions work better
        # (otherwise we'd need to generate and load fields in a way that
        # packetinstructions understands)
        descriptor = "(" + self.dynamic_desc.args_descriptor + \
                        self.instantiated_desc.args_descriptor + ")" + \
                        self.instantiated_desc.returns_descriptor
        method = self.generated_cf.methods.create(self.dynamic_name,
                                                  descriptor, code=True)
        self.generated_method = method
        # Similar hack: make the method static, so that packetinstructions
        # doesn't look for the corresponding instance.
        method.access_flags.acc_static = True
        # Third hack: the extra arguments are in the local variables/arguments
        # list, not on the stack.  So we need to move them to the stack.
        # (In a real implementation, these would probably be getfield instructions)
        # Also, this uses aload for everything, instead of using the appropriate
        # instruction for each type.
        instructions = []
        for i in range(len(method.args)):
            instructions.append(("aload", i))

        cls_ref = self.generated_cf.constants.create_class(self.method_class)
        if self.ref_kind in FIELD_REFS:
            # This case is not currently hit, but provided for future use
            # (Likely method_name and method_descriptor would no longer be used though)
            ref = self.generated_cf.constants.create_field_ref(
                    self.method_class, self.method_name, self.method_desc.descriptor)
        elif self.ref_kind == REF_invokeInterface:
            ref = self.generated_cf.constants.create_interface_method_ref(
                    self.method_class, self.method_name, self.method_desc.descriptor)
        else:
            ref = self.generated_cf.constants.create_method_ref(
                    self.method_class, self.method_name, self.method_desc.descriptor)

        # See https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-5.html#jvms-5.4.3.5
        if self.ref_kind == REF_getField:
            instructions.append(("getfield", ref))
        elif self.ref_kind == REF_getStatic:
            instructions.append(("getstatic", ref))
        elif self.ref_kind == REF_putField:
            instructions.append(("putfield", ref))
        elif self.ref_kind == REF_putStatic:
            instructions.append(("putstatic", ref))
        elif self.ref_kind == REF_invokeVirtual:
            instructions.append(("invokevirtual", ref))
        elif self.ref_kind == REF_invokeStatic:
            instructions.append(("invokestatic", ref))
        elif self.ref_kind == REF_invokeSpecial:
            instructions.append(("invokespecial", ref))
        elif self.ref_kind == REF_newInvokeSpecial:
            instructions.append(("new", cls_ref))
            instructions.append(("dup",))
            instructions.append(("invokespecial", ref))
        elif self.ref_kind == REF_invokeInterface:
            instructions.append(("invokeinterface", ref))

        method.code.assemble(assemble(instructions))

        return (self.generated_cf, self.generated_method)

class StringConcatInvokeDynamicInfo(InvokeDynamicInfo):
    """
    Java 9+ uses invokedynamic for string concatenation:
    https://www.guardsquare.com/blog/string-concatenation-java-9-untangling-invokedynamic
    """
    # An example:
    """
    public static String foo(int num, int num2) {
      return "num=" + num + " and num2=" + num2;
    }
    """
    # Becomes:
    """
    Constant pool:
      #7 = InvokeDynamic      #0:#8          // #0:makeConcatWithConstants:(II)Ljava/lang/String;
    public static java.lang.String foo(int, int);
      descriptor: (II)Ljava/lang/String;
      flags: (0x0009) ACC_PUBLIC, ACC_STATIC
      Code:
        stack=2, locals=2, args_size=2
           0: iload_0
           1: iload_1
           2: invokedynamic #7,  0              // InvokeDynamic #0:makeConcatWithConstants:(II)Ljava/lang/String;
           7: areturn
        LineNumberTable:
          line 3: 0
    BootstrapMethods:
      0: #19 REF_invokeStatic -snip- StringConcatFactory.makeConcatWithConstants -snip-
        Method arguments:
          #25 num=\u0001 and num2=\u0001
    """
    # Note that the format string can have \u0002 in it as well to indicate a constant.
    # I haven't seen any cases of \u0002 yet.

    def __init__(self, ins, cf, const):
        super().__init__(ins, cf, const)

        bootstrap = cf.bootstrap_methods[const.method_attr_index]
        method = cf.constants.get(bootstrap.method_ref)
        # Make sure this is a reference to StringConcatFactory.makeConcatWithConstants
        assert method.reference_kind == REF_invokeStatic
        assert method.reference.class_.name == "java/lang/invoke/StringConcatFactory"
        assert method.reference.name_and_type.name == "makeConcatWithConstants"
        assert len(bootstrap.bootstrap_args) == 1 # Num arguments - may change with constants

        # Now check the arguments.  Note that StringConcatFactory has some
        # arguments automatically filled in.  The bootstrap arguments are:
        # args[0] is recipe, format string
        # Further arguments presumably go into the constants varargs array, but I haven't seen this
        # (and I'm not sure how you get a constant that can't be converted to a string at compile time)
        self.recipe = cf.constants.get(bootstrap.bootstrap_args[0]).string.value
        assert '\u0002' not in self.recipe

        self.dynamic_name = const.name_and_type.name.value
        self.dynamic_desc = method_descriptor(const.name_and_type.descriptor.value)

        assert self.dynamic_desc.returns.name == "java/lang/String"

    def __str__(self):
        recipe = self.recipe.replace("\u0001", "\\u0001").replace("\u0002", "\\u0002")
        if (self.stored_args == None):
            return "format_concat(\"%s\", ...)" % (recipe,)
        else:
            return "format_concat(\"%s\", %s)" % (recipe, ", ".join(str(a) for a in self.stored_args))

    def create_method(self):
        raise NotImplementedError()

def class_from_invokedynamic(ins, cf):
    """
    Gets the class type for an invokedynamic instruction that
    calls a constructor.
    """
    info = InvokeDynamicInfo.create(ins, cf)
    assert info.created_type != "void"
    return info.created_type

def try_eval_lambda(ins, args, cf):
    """
    Attempts to call a lambda function that returns a constant value.
    May throw; this code is very hacky.
    """
    info = InvokeDynamicInfo.create(ins, cf)
    # We only want to deal with lambdas in the same class
    assert info.ref_kind == REF_invokeStatic
    assert info.method_class == cf.this.name

    lambda_method = cf.methods.find_one(name=info.method_name, args=info.method_desc.args_descriptor, returns=info.method_desc.returns_descriptor)
    assert lambda_method != None

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

def string_from_invokedymanic(ins, cf):
    """
    Gets the recipe string for a string concatenation implemented via invokedynamc.
    """
    info = InvokeDynamicInfo.create(ins, cf)
    assert isinstance(info, StringConcatInvokeDynamicInfo)
    return info.recipe

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
