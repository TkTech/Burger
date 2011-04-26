#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2010-2011 Tyler Kennedy <tk@tkte.ch>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
__all__ = [
    "Context",
    "ContextError"
]

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from functools import wraps
from collections import defaultdict

from ..classfile import ConstantType
from ..bytecode import StreamDisassembler
from ..descriptor import method_descriptor

class Event(object):
    def __init__(self):
        self.__handlers = set()
        
    def __iadd__(self, handler):
        self.__handlers.add(handler)
        return self
        
    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self
        
    def fire(self, *args, **keywargs):
        for handler in self.__handlers:
            handler(*args, **keywargs)

class ContextError(Exception):
    """
    Raised when any generic error occurs while attempting to
    run a method.
    """

class Context(object):
    def __init__(self, classfile, types=None):
        """
        Constructs and wraps a Context around `classfile`.
        """
        self.cf = classfile
        self.type_map = {} if not types else types

        self.fields = {}
        for field in classfile.fields.find():
            self.fields[field.name] = field._asdict()

        self.hooks = defaultdict(Event)

    def run(self, name, args=None, stack=None):
        """
        Attempt to run the method `name` which accepts `args`.
        `args` (if specified) is a list of tuples in the form of:
            ("<type>", value)
        Explicitly stating the type is required as Java allows method 
        overloading. An example for the Java methods:
            public void println(String x)
            public void println(int x)
        would be:
            >>> run("println", [("java.lang.String", "Hello World!")])
            >>> run("println", [("int", 6)])
        """
        if args:
            types, values = zip(*args)
        else:
            types, values = None, None

        locals_ = values

        cf = self.cf

        methods = cf.methods.find(name=name, args=types)
        if not methods:
            raise ContextError("no method with that signature")

        # There can only be one function with a matching signature,
        # if there's more than one you need to be more explicity with
        # the arguments.
        if len(methods) != 1:
            raise ContextError("ambiguous method signature")

        method = methods[0]

        # Todo: Caching
        code = StringIO(method.code.code)
        dism = StreamDisassembler(code)

        if not stack:
            stack = []

        for ins in dism.iter_ins():
            if hasattr(self, "_i_%s" % ins.name):
                getattr(self, "_i_%s" % ins.name)(ins, locals_, stack)
            else:
                raise ContextError(
                    "unimplemented opcode {%s}" % ins.name)

    def lookup_class(self, reference):
        reference = reference.replace("/", ".")
        return self.type_map.get(reference, None)

    def _i_new(self, ins, locals_, stack):
        """
        Create new object.
        ...=>
        ...,objectref
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]
        name = const["name"]["value"]
        obj = self.lookup_class(name)
        if not obj:
            raise ContextError("unknown object {%s}" % name)
        stack.append(obj())

    def _i_dup(self, ins, locals_, stack):
        """
        Duplicate the top operand stack value.
        ...,value =>
        ...,value, value
        """
        stack.append(stack[-1])

    def _i_invokespecial(self, ins, locals_, stack):
        """
        Invoke instance method; special handling for superclass, private, and
        instance initialization method invocations.
        ...,objectref,[arg1,arg2 ...]] =>
        ...
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]

        class_name = const["class"]["name"]["value"]
        obj = self.lookup_class(class_name)

        method_name = const["name_and_type"]["name"]["value"]
        method_type = const["name_and_type"]["descriptor"]["value"]

        args, rets = method_descriptor(method_type)
        if len(args):
            values = stack[-len(args):]
            del stack[-len(args):]
        else:
            values = []

        instance = stack.pop()

        if method_name == "<clinit>":
            method_name = "_static_constructor_"
        elif method_name == "<init>":
            method_name = "_constructor_"

        if hasattr(obj, method_name):
            method = getattr(obj, method_name)
            pack_args = zip(args, values)

            returned = method(instance, "public", pack_args)
            if returned is not None:
                stack.append(returned)

            self.hooks["invokespecial"].fire(const, pack_args, returned) 
        else:
            raise ContextError(
                    "unimplemented method {%s(%s)}" % (
                        method_name, ", ".join(args)))

    def _i_invokestatic(self, ins, locals_, stack):
        """
        Invoke a class (static) method.
        ...,[arg1,[arg2 ...]] =>
        ...
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]

        class_name = const["class"]["name"]["value"]

        method_name = const["name_and_type"]["name"]["value"]
        method_type = const["name_and_type"]["descriptor"]["value"]

        args, rets = method_descriptor(method_type)

        if len(args):
            values = stack[-len(args):]
            del stack[-len(args):]
        else:
            values = []

        pack_args = zip(args, values)

        if class_name == self.cf.this:
            # We're going to be calling ourselves
            returned = self.run(method_name, pack_args, stack)
            if returned is not None:
                stack.append(returned)
        else:
            # Calling an external class
            obj = self.lookup_class(class_name)
            # <clinit> is an illegal function name in Python,
            # so we use _static_constructor_ instead.
            if method_name == "<clinit>":
                method_name = "_static_constructor_"

            if not hasattr(obj, method_name):
                raise ContextError("unimplemented method %s" % const)

            method = getattr(obj, method_name)
            returned = method("public", pack_args)

            if returned is not None:
                stack.append(returned)

        self.hooks["invokestatic"].fire(const, pack_args, returned) 

    def _i_putstatic(self, ins, locals_, stack):
        """
        Set static field in class.
        ...,value =>
        ...
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]

        class_name = const["class"]["name"]["value"]
        field_name = const["name_and_type"]["name"]["value"]

        if class_name == self.cf.this:
            # Working on the class wrapped by Context
            self.fields[field_name]["value"] = stack.pop()
        else:
            obj = self.lookup_class(class_name)
            if not hasattr(obj, "_fields_"):
                setattr(obj, "_fields_", {})

            obj._fields_[field_name] = stack.pop()

    def _i_getstatic(self, ins, locals_, stack):
        """
        Get static field from class.
        ...,=>
        ...,value
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]

        class_name = const["class"]["name"]["value"]
        field_name = const["name_and_type"]["name"]["value"]

        if class_name == self.cf.this:
            return self.fields[field_name]["value"]
        else:
            obj = self.lookup_class(class_name)
            return obj._fields_[field_name]

    def _i_iconst_0(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(0)

    def _i_iconst_1(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(1)

    def _i_iconst_2(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(2)

    def _i_iconst_3(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(3)

    def _i_iconst_4(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(4)

    def _i_iconst_5(self, ins, locals_, stack):
        """
        Push int constant.
        ... =>
        ...,<i>
        """
        stack.append(5)

    def _i_iload_0(self, ins, locals_, stack):
        """
        Load int from local variable.
        ... =>
        ...,value
        """
        stack.append(locals_[0])

    def _i_ldc(self, ins, locals_, stack):
        """
        Push item from runtime constant pool.
        ... =>
        ...,value
        """
        const_i = ins.operands[0].value
        const = self.cf.constants[const_i]
        stack.append(const)

    @staticmethod
    def scope_public(f):
        @wraps(f)
        def scope(self, scope, *args, **kwargs):
            if scope != "public":
                raise RuntimeError(scope)

            return f(self, *args, **kwargs)
        return scope

    @staticmethod
    def scope_protected(f):
        @wraps(f)
        def scope(self, scope, *args, **kwargs):
            if scope != "protected":
                raise RuntimeError(scope)

            return f(self, *args, **kwargs)
        return scope

    @staticmethod
    def scope_private(f):
        @wraps(f)
        def scope(self, scope, *args, **kwargs):
            if scope != "private":
                raise RuntimeError(scope)

            return f(self, *args, **kwargs)
        return scope

    @staticmethod
    def scope_any(f):
        """Ignores any scope restrictions."""
        @wraps(f)
        def scope(scope, *args, **kwargs):
            return f(*args, **kwargs)
        return scope
        
        
