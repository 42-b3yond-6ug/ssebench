# Segmentation Fault in _curses

## Crash report

What happened?

### Build

```
./configure --with-pydebug --with-address-sanitizer
apt-get install libncurses5-dev
```

### Root Cause

When calling _curses.initscr, initialised is set to True. Then, if _curses.resizeterm is called with an improper size for the first argument, an error occurs, and stdscr is freed. The error does not terminate even when wrapped in a try-except block.
Because initialised is set to True, a second call to _curses.initscr invokes wrefresh(stdscr) even though stdscr has already been freed.

cpython/Modules/_cursesmodule.c
```
 _curses_initscr_impl(PyObject *module) 
 /*[clinic end generated code: output=619fb68443810b7b input=514f4bce1821f6b5]*/ 
 { 
     WINDOW *win; 
     PyCursesWindowObject *winobj; 
  
     if (initialised) { 
         wrefresh(stdscr); 
         return (PyObject *)PyCursesWindow_New(stdscr, NULL); 
     } 
  
     win = initscr(); 
  
     if (win == NULL) { 
         PyErr_SetString(PyCursesError, catchall_NULL); 
         return NULL; 
     } 
  
     initialised = initialised_setupterm = TRUE; 
```

### POC

```
import _curses
_curses.initscr()
try:
    _curses.resizeterm(+35000, 1)
except:
    pass
_curses.initscr()
```

### ASAN

```

AddressSanitizer:DEADLYSIGNAL
=================================================================
==1373==ERROR: AddressSanitizer: SEGV on unknown address 0x7f4c7b59d370 (pc 0x7f4c7b7eb5aa bp 0x61b000018880 sp 0x7ffd073842c0 T0)
==1373==The signal is caused by a READ memory access.
#0 0x7f4c7b7eb5aa  (/lib/x86_64-linux-gnu/libncursesw.so.6+0x275aa)
#1 0x7f4c7b7edd09 in doupdate_sp (/lib/x86_64-linux-gnu/libncursesw.so.6+0x29d09)
#2 0x7f4c7b7e16d7 in wrefresh (/lib/x86_64-linux-gnu/libncursesw.so.6+0x1d6d7)
#3 0x7f4c7b9908f6 in _curses_initscr_impl Modules/_cursesmodule.c:3258
#4 0x7f4c7b999675 in _curses_initscr Modules/clinic/_cursesmodule.c.h:2661
#5 0x562817924edd in cfunction_vectorcall_NOARGS Objects/methodobject.c:481
#6 0x5628175fddeb in _PyObject_VectorcallTstate Include/internal/pycore_call.h:92
#7 0x5628175fe0a0 in PyObject_Vectorcall Objects/call.c:325
#8 0x56281800d628 in _PyEval_EvalFrameDefault Python/bytecodes.c:2706
#9 0x5628180346d0 in _PyEval_EvalFrame Include/internal/pycore_ceval.h:89
#10 0x5628180346d0 in _PyEval_Vector Python/ceval.c:1683
#11 0x562818034a7c in PyEval_EvalCode Python/ceval.c:578
#12 0x562818377486 in run_eval_code_obj Python/pythonrun.c:1691
#13 0x56281837cb70 in run_mod Python/pythonrun.c:1712
#14 0x56281837d4f1 in pyrun_file Python/pythonrun.c:1612
#15 0x562818397728 in _PyRun_SimpleFileObject Python/pythonrun.c:433
#16 0x562818398a0c in _PyRun_AnyFileObject Python/pythonrun.c:78
#17 0x5628184e2cf0 in pymain_run_file_obj Modules/main.c:360
#18 0x5628184e4c04 in pymain_run_file Modules/main.c:379
#19 0x5628184f0722 in pymain_run_python Modules/main.c:629
#20 0x5628184f0be4 in Py_RunMain Modules/main.c:709
#21 0x5628184f1077 in pymain_main Modules/main.c:739
#22 0x5628184f14f4 in Py_BytesMain Modules/main.c:763
#23 0x562817147c3a in main Programs/python.c:15
#24 0x7f4c7ec56d8f in __libc_start_call_main ../sysdeps/nptl/libc_start_call_main.h:58
#25 0x7f4c7ec56e3f in __libc_start_main_impl ../csu/libc-start.c:392
#26 0x562817072344 in _start (/cpython/python+0x3a7344)
AddressSanitizer can not provide additional info.
SUMMARY: AddressSanitizer: SEGV (/lib/x86_64-linux-gnu/libncursesw.so.6+0x275aa)
==1373==ABORTING
```

### CPython versions tested on:
CPython main branch

### Operating systems tested on:
Linux

### Output from running 'python -VV' on the command line:
Python 3.14.0a0 (heads/main:34f5ae69fe, Jun 9 2024, 21:27:54) [GCC 11.4.0]
