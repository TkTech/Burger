# Burger
Burger is a tiny "framework" for automatically extracting data
from the minecraft game for the purpose of writing the protocol
specification, interoperability, and other neat uses.

## The Idea
Burger is made up of *toppings*, which can provide and satisfy
simple dependencies, and which can be run all-together or just
a few specifically. Each topping is then aggregated by
`munch.py` into the whole and output as a JSON dictionary.

## Usage
The simplest way to use Burger is to pass the `-d` or `--download`
flag, which will download the minecraft client for you.

    $ python munch.py --download

Alternatively, you can specify either the client or the server
JAR by passing it as an argument.

    $ python munch.py minecraft_server.jar

We can redirect the output from the default `stdout` by passing
`-o <path>` or `--output <path>`.
    
    $ python munch.py -d --output output.json

We can see what toppings are available by passing `-l` or `--list`.

    $ python munch.py --list

We can also run specific toppings by passing a comma-delimited list
to `-t` or `--toppings`. If a topping cannot be used because it's
missing a dependency, it will output an error telling you what 
also needs to be included.

    $ python munch.py -d --toppings language,stats

The above example would only extract the language information, as
well as the stats and achievements (both part of `stats`).

=======
# Solum
Solum is [intended] to be a very simple library for inspecting and disassembling JVM class files.

**Note**: When poking around, keep in mind that you can `print` just about everything returned by methods of `ClassFile`. This can give you quick insight into what's available.

## Playing with JAR files
First and foremost, remember that JAR's are just .zip files with a different extension. You can access Python's ZipFile instance as the `zp` property of a JarFile(). The `JarFile` class exists to make a few Java-specific tasks easier.

### Opening a Jar
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
```

### Getting the contents of a single file
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    print jar.read("title/splashes.txt")
```

### Getting a class
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    cf = jar.open_class("HelloWorld")  # The .class is optional
```

## Playing with .class files
Every class in Java is represented by a .class file. The entire contents of a class is available within the context of one of these files.

### Opening a .class
Opening these directly using Solum is as painless as opening a Jar.

```python
from solum import ClassFile

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    print cf.this # Prints "HelloWorld"
    print cf.superclass # Prints "java/lang/object"
```

### Finding Constants, Fields, and Methods
Every reference to a class, field, string, integer, etc... is stored as a constant. We can easily search for everything or narrow it down by various criteria. Getting all of the constants is achieved by doing a search without any criteria.

```python
from solum import ClassFile

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    # Return all of the constants in the file
    print cf.constants.find()
```

This usually isn't very useful by itself, so we want to narrow it down. Lets say we want to get all constants that represents strings in the program.

```python
from solum import ClassFile, ConstantType

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    # Return all of the strings in the class
    print cf.constants.find(ConstantType.STRING)
```

In our ```HelloWorld.class``` example, this predictably has just one result,

```
[{'tag': 8, 'string': {'tag': 1, 'value': 'Hello, World'}, 'string_index': 18}]
```

Lets try this another way. Instead of searching just for strings put in there by the programmer, we'll get all of the text in the class. But hey, we also only want to find it if it's less than 6 characters.

```python
from solum import ClassFile, ConstantType

def test(constant):
    return len(constant["value"]) < 6

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    print cf.constants.find(ConstantType.UTF8, f=test)
```

This example will call the function given in `f` for each constant of type `UTF8`, and only return those for which `test()` returns `True`. This gives us a lot of flexibility in getting only what we really want.

We can also make use of `find_one()`, which will return the first valid match or `None` if there was none.

```python
from solum import ClassFile, ConstantType

def test(constant):
    return "Hello" in constant["value"]

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    print cf.constants.find_one(ConstantType.UTF8, f=test)
```

Fields and methods have similar interfaces. Want to find all methods that return void?

```python
from solum import ClassFile, ConstantType

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    print cf.methods.find(returns="void")
```

How about only those named "max" that take two integers?

```python
from solum import ClassFile

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    print cf.methods.find(name="max", args=("integer", "integer"))
```

## Method Disassembly
Disassembly is just as easy. Simply find the method(s) you want to disassemble, and iterate over their `instructions` property. To see what other methods are available on the `instructions` property, take a look at the `Disassembler()` class in bytecode.py.

```python
from solum import ClassFile

if __name__ == "__main__":
    cf = ClassFile("HelloWorld.class")
    main = cf.methods.find_one(name="main")

    for ins in main.instructions:
        print ins
```
