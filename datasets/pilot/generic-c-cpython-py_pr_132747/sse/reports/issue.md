# SIGSEV with method descriptors called without a second argument

## Crash report

### What happened?

Since Python 3.12, the following code triggers a segmentation fault:

```
import _io, sys; _io._TextIOBase.detach.__get__(sys.stderr)
```

### CPython versions tested on:
3.9, 3.11, 3.12, 3.13, 3.14

### Operating systems tested on:
Linux

### Output from running 'python -VV' on the command line:
No response
