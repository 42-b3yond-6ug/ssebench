# [3.13] Crash when generator frame proxies outlive their generator

## Crash report

### What happened?

Checking some frame proxy behaviour at the interactive prompt, I encountered the following crash:

```
$ PYTHON_BASIC_REPL=1 python3.13
Python 3.13.0 (main, Oct  8 2024, 00:00:00) [GCC 14.2.1 20240912 (Red Hat 14.2.1-3)] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import sys
>>> def g():
...     a = 1
...     yield locals(), sys._getframe().f_locals
...
>>> snapshot, live_locals = next(g())
>>> print(snapshot); print(live_locals)
{'a': 1}
{'a': b'print'}
>>> snapshot, live_locals = next(g())
>>> print(snapshot); print(live_locals)
{'a': 1}
{'a': 'input_trans_stack'}
>>> snapshot, live_locals = next(g())
>>> print(snapshot); print(live_locals)
{'a': 1}
Segmentation fault (core dumped)
```

(Crash was initially seen in the new REPL, the above reproduction in the basic REPL showed it wasn't specific to the new REPL).

Subsequent investigation suggests that the problem relates to the frame proxy outliving the eval loop that created it, as the following script was able to reliably reproduce the crash (as shown below):

```
import sys
def g():
    a = 1
    yield locals(), sys._getframe().f_locals
ns = {}
for i in range(10):
    exec("snapshot, live_locals = next(g())", locals=ns)
    print(ns)
```

```
$ python3.13 ../_misc/gen_locals_exec.py
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': '_pickle.cpython-313-x86_64-linux-gnu.so'}}
Segmentation fault (core dumped)
```

Changing the code to explicitly keep the generator object alive:

```
import sys
def g():
    a = 1
    yield locals(), sys._getframe().f_locals
ns = {}
for i in range(10):
    gen = g()
    exec("snapshot, live_locals = next(gen)", locals=ns)
    print(ns)
```

is sufficient to eliminate the crash:

```
$ python3.13 ../_misc/gen_locals_exec.py
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
```

The crash is still eliminated, even when gen is created via exec rather than creating it in the main eval loop:

```
import sys
def g():
    a = 1
    yield locals(), sys._getframe().f_locals
ns = {}
for i in range(10):
    exec("gen = g()", locals=ns)
    exec("snapshot, live_locals = next(gen)", locals=ns)
    print(ns)
```

```
$ python3.13 ../_misc/gen_locals_exec.py
{'gen': <generator object g at 0x7f8da7d81b40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81e40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81c00>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81b40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81e40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81c00>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81b40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81e40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81c00>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
{'gen': <generator object g at 0x7f8da7d81b40>, 'snapshot': {'a': 1}, 'live_locals': {'a': 1}}
```

### CPython versions tested on:
3.13, CPython main branch

### Operating systems tested on:
Linux

### Output from running 'python -VV' on the command line:
No response
