# Solum
Solum is [intended] to be a very simple library for inspecting and disassembling JVM class files.

**Note**: When poking around, keep in mind that you can `print` just about everything returned by methods of `ClassFile`. This can give you quick insight into what's available.

## Playing with JAR files
### Opening a Jar
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
```
### Getting the manifest
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    print jar.manifest
```

### Listing files
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    # Print all non-class files
    for other in jar.other:
        print other.filename
    # Print all classes
    for class_ in jar.classes:
        print class_.filename
```

### Getting the contents of a single file
```python
import sys
from solum import JarFile

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    print jar["title/splashes.txt"]
```

### Mapping
This is where things start to become interesting. Using the JarFile's mapping functions, we can efficiently operate over sets of files.

```python
import sys
from solum import JarFile

def map_test(buff):
    pass

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    results = jar.map(map_test)
```

By default, this will map every .class file present in the JAR, returning a list of return values from `map_test`. We can also specify only a few files to work with by passing them into `files`.

```python

import sys
from solum import JarFile

def map_test(buff):
    pass

if __name__ == "__main__":
    jar = JarFile(sys.argv[1])
    results = jar.map(map_test, files=jar.other)
```

We can also ask it to map the files using the `multiprocessing` module when available by passing `parallel=True`. Remember to account for the quirks in the `multiprocessing` module if you're using this.

```python
results = jar.map(map_test, files=jar.other, parallel=True)
````

## Playing with .class files
Every class in Java is represented by a .class file. The entire contents of a class is available within  the context of one of these files.

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

