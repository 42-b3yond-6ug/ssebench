# Possible race condition in signal handling

The following code segfaults the interpreter on Linux. Tested on current main.

```
import gc
import _thread

gc.set_threshold(1, 0, 0)

def cb(*args):
    _thread.interrupt_main()


gc.callbacks.append(cb)

def gen():
    yield 1

g = gen()
g.__next__()
```

```
Exception ignored in: <function cb at 0x7f7f4f6fe200>
Traceback (most recent call last):
  File "/workspaces/cpython/main.py", line 7, in cb
    _thread.interrupt_main()
KeyboardInterrupt: 
Exception ignored in: <function cb at 0x7f7f4f6fe200>
Traceback (most recent call last):
  File "/workspaces/cpython/main.py", line 7, in cb
    _thread.interrupt_main()
KeyboardInterrupt: 
Exception ignored in: <function cb at 0x7f7f4f6fe200>
Traceback (most recent call last):
  File "/workspaces/cpython/main.py", line 7, in cb
    _thread.interrupt_main()
KeyboardInterrupt: 
Exception ignored in: <function cb at 0x7f7f4f6fe200>
Traceback (most recent call last):
  File "/workspaces/cpython/main.py", line 7, in cb
    _thread.interrupt_main()
KeyboardInterrupt: 
Segmentation fault (core dumped)
```
