# framelocalsproxy_new() crash if called with no arguments

## Bug report

Example on Python 3.13.0rc2:

```
$ python3.13
>>> import sys
>>> FrameLocalsProxy=type([sys._getframe().f_locals for x in range(1)][0])
... 
>>> FrameLocalsProxy()
Erreur de segmentation (core dumped)
```
