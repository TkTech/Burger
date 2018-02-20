def class_from_invokedynamic(ins, cf):
    """
    Gets the class type for an invokedynamic instruction that
    calls a constructor.
    """
    # Temporary, until the attribute is properly exposed
    bootstrap_methods = cf.attributes.find_one("BootstrapMethods")
    assert bootstrap_methods is not None

    const = cf.constants.get(ins.operands[0].value)
    bootstrap = bootstrap_methods.table[const.method_attr_index]
    method = cf.constants.get(bootstrap[0])
    # Make sure this is a reference to LambdaMetafactory
    assert method._reference_kind == 6 # REF_invokeStatic
    assert method.reference.class_.name.value == "java/lang/invoke/LambdaMetafactory"
    assert method.reference.name_and_type.name.value == "metafactory"
    assert bootstrap[1] == 3 # Num arguments
    # Now check the arguments.  Note that LambdaMetafactory has some
    # arguments automatically filled in.
    methodhandle = cf.constants.get(bootstrap[2][1])
    assert methodhandle._reference_kind == 8 # REF_newInvokeSpecial
    assert methodhandle.reference.name_and_type.name.value == "<init>"
    # OK, now that we've done all those checks, just get the type
    # from the constructor.
    return methodhandle.reference.class_.name.value