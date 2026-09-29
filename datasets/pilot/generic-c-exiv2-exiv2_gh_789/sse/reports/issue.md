# SIGSEGV in PngImage::readMetadata()

There is a bug at pngimage.cpp:469. If `iccOffset == 0`, which happens if `chunkLength == 0`, then Exiv2 crashes with a SIGSEGV.

Here is the PoC, which I have tested on master: [poc1](poc1.png). You can run the PoC like this:

```
$ exiv2 poc1.png
Segmentation fault (core dumped)
```
