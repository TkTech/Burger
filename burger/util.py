def class_from_invokedynamic(ins, cf):
    """
    Gets the class type for an invokedynamic instruction that
    calls a constructor.
    """
    const = cf.constants.get(ins.operands[0].value)
    bootstrap = cf.bootstrap_methods[const.method_attr_index]
    method = cf.constants.get(bootstrap.method_ref)
    # Make sure this is a reference to LambdaMetafactory
    assert method.reference_kind == 6 # REF_invokeStatic
    assert method.reference.class_.name.value == "java/lang/invoke/LambdaMetafactory"
    assert method.reference.name_and_type.name.value == "metafactory"
    assert len(bootstrap.bootstrap_args) == 3 # Num arguments
    # Now check the arguments.  Note that LambdaMetafactory has some
    # arguments automatically filled in.
    methodhandle = cf.constants.get(bootstrap.bootstrap_args[1])
    assert methodhandle.reference_kind == 8 # REF_newInvokeSpecial
    assert methodhandle.reference.name_and_type.name.value == "<init>"
    # OK, now that we've done all those checks, just get the type
    # from the constructor.
    return methodhandle.reference.class_.name.value