# UAF: xml.etree.ElementTree.Element.remove when concurrent mutations happen

## Crash report

### What happened?

A UAF in Element.remove was fixed but one can mutate the child's list during .remove and cause an OOB crash:

```
import xml.etree.ElementTree as ET

class EvilElement(ET.Element):
    def __eq__(self, other):
        base.clear()
        return False

base = ET.Element('a')
base.append(EvilElement('a'))
base.append(EvilElement('a'))
base.remove(ET.Element('b'))
```

Attacked code:

```
for (i = 0; i < self->extra->length; i++) { 
     if (self->extra->children[i] == subelement) 
         break; 
     rc = PyObject_RichCompareBool(self->extra->children[i], subelement, Py_EQ); 
     if (rc > 0) 
         break; 
     if (rc < 0) 
         return NULL; 
 }
```

I think we need to introduce some state integer to check that there is no evil mutation (similar to what's being done for OrderedDict).

### CPython versions tested on:
CPython main branch

### Operating systems tested on:
No response

### Output from running 'python -VV' on the command line:
No response
