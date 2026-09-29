# Segmentation fault with cyclic imports

To reproduce create two files a.mjs and b.mjs and run qjs a.mjs.

a.mjs:

```
import { fb } from "./b.mjs";
export { fb };
```

b.mjs:

```
import * as $a from "a.mjs";
export function fb() {};
```

There is no crash if export` { fb };` is removed from a.mjs or the import in b.mjs is changed to `import {} from "a.mjs";`.

```
AddressSanitizer:DEADLYSIGNAL
=================================================================
==277778==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000000 (pc 0x0000004fbc1c bp 0x7ffcc9070200 sp 0x7ffcc90700c0 T0)
==277778==The signal is caused by a WRITE memory access.
==277778==Hint: address points to the zero page.
    #0 0x4fbc1c in js_build_module_ns /quickjs/quickjs.c:28041
    #1 0x4fc144 in JS_GetModuleNamespace /quickjs/quickjs.c:28076
    #2 0x58bf20 in js_inner_module_linking /quickjs/quickjs.c:28333
    #3 0x58b7e3 in js_inner_module_linking /quickjs/quickjs.c:28268
    #4 0x5a175d in js_link_module /quickjs/quickjs.c:28441
    #5 0x5a175d in JS_EvalFunctionInternal /quickjs/quickjs.c:34409
    #6 0x5a2487 in JS_EvalFunction /quickjs/quickjs.c:34425
    #7 0x40bec9 in eval_buf /quickjs/qjs.c:67
    #8 0x40bff5 in eval_file /quickjs/qjs.c:103
    #9 0x40b050 in main /quickjs/qjs.c:516
    #10 0x7ff77b15a10d in __libc_start_call_main (/nix/store/k7zgvzp2r31zkg9xqgjim7mbknryv6bs-glibc-2.39-52/lib/libc.so.6+0x2a10d) (BuildId: bc8ec5f3ac2561de8f08b232685038c7167bf4b7)
    #11 0x7ff77b15a1c8 in __libc_start_main_alias_1 (/nix/store/k7zgvzp2r31zkg9xqgjim7mbknryv6bs-glibc-2.39-52/lib/libc.so.6+0x2a1c8) (BuildId: bc8ec5f3ac2561de8f08b232685038c7167bf4b7)
    #12 0x40b584 in _start (/quickjs/qjs+0x40b584)

AddressSanitizer can not provide additional info.
SUMMARY: AddressSanitizer: SEGV /quickjs/quickjs.c:28041 in js_build_module_ns
==277778==ABORTING
```
