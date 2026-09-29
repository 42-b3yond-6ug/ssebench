# UAF in SplDoublyLinked->serialize()

## Description

The following code:

```
<?php

class C {
    function __serialize(): array {
        global $list;
        $list->pop();
        return [];
    }
}

$list = new SplDoublyLinkedList;
$list->add(0, new C);
$list->add(1, 1);
$list->serialize();
```

Resulted in this output:

```
==954815==ERROR: AddressSanitizer: heap-use-after-free on address 0x60300002a7f8 at pc 0x561f8aa2da49 bp 0x7ffdb5430df0 sp 0x7ffdb5430de8
READ of size 8 at 0x60300002a7f8 thread T0
    #0 0x561f8aa2da48 in zim_SplDoublyLinkedList_serialize /tmp/php-asan/ext/spl/spl_dllist.c:1014:19
    #1 0x561f8b29f2d2 in ZEND_DO_FCALL_SPEC_RETVAL_UNUSED_HANDLER /tmp/php-asan/Zend/zend_vm_execute.h:1919:4
    #2 0x561f8b1b183d in execute_ex /tmp/php-asan/Zend/zend_vm_execute.h:58565:7
    #3 0x561f8b1b2067 in zend_execute /tmp/php-asan/Zend/zend_vm_execute.h:64217:2
    #4 0x561f8b5e6860 in zend_execute_script /tmp/php-asan/Zend/zend.c:1932:3
    #5 0x561f8ae04d2b in php_execute_script_ex /tmp/php-asan/main/main.c:2574:13
    #6 0x561f8ae05228 in php_execute_script /tmp/php-asan/main/main.c:2614:9
    #7 0x561f8b5ee309 in do_cli /tmp/php-asan/sapi/cli/php_cli.c:935:5
    #8 0x561f8b5eb32c in main /tmp/php-asan/sapi/cli/php_cli.c:1310:18
    #9 0x7f2f8ee29d8f in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:58:16
    #10 0x7f2f8ee29e3f in __libc_start_main csu/../csu/libc-start.c:392:3
    #11 0x561f8a002de4 in _start (/workspaces/TriFuzz/targets/php-asan/bin/php+0x402de4)

0x60300002a7f8 is located 8 bytes inside of 32-byte region [0x60300002a7f0,0x60300002a810)
freed by thread T0 here:
    #0 0x561f8a087702 in free /opt/llvm-15-build/llvm-15.x/final/llvm-project/compiler-rt/lib/asan/asan_malloc_linux.cpp:52:3
    #1 0x561f8b0418a3 in __zend_free /tmp/php-asan/Zend/zend_alloc.c:3308:2
    #2 0x561f8b045774 in _efree /tmp/php-asan/Zend/zend_alloc.c:2747:3
    #3 0x561f8aa27206 in spl_ptr_llist_pop /tmp/php-asan/ext/spl/spl_dllist.c:219:2
    #4 0x561f8aa26c6e in zim_SplDoublyLinkedList_pop /tmp/php-asan/ext/spl/spl_dllist.c:516:2
    #5 0x561f8b29f2d2 in ZEND_DO_FCALL_SPEC_RETVAL_UNUSED_HANDLER /tmp/php-asan/Zend/zend_vm_execute.h:1919:4
    #6 0x561f8b1b183d in execute_ex /tmp/php-asan/Zend/zend_vm_execute.h:58565:7
    #7 0x561f8b18d1ac in zend_call_function /tmp/php-asan/Zend/zend_execute_API.c:996:3
    #8 0x561f8b18f3b2 in zend_call_known_function /tmp/php-asan/Zend/zend_execute_API.c:1090:23
    #9 0x561f8ad7219a in zend_call_known_instance_method /tmp/php-asan/Zend/zend_API.h:860:2
    #10 0x561f8ad7210b in zend_call_known_instance_method_with_0_params /tmp/php-asan/Zend/zend_API.h:866:2
    #11 0x561f8ad70778 in php_var_serialize_call_magic_serialize /tmp/php-asan/ext/standard/var.c:850:2
    #12 0x561f8ad6833d in php_var_serialize_intern /tmp/php-asan/ext/standard/var.c:1147:10
    #13 0x561f8ad67501 in php_var_serialize /tmp/php-asan/ext/standard/var.c:1321:2
    #14 0x561f8aa2da74 in zim_SplDoublyLinkedList_serialize /tmp/php-asan/ext/spl/spl_dllist.c:1016:3
    #15 0x561f8b29f2d2 in ZEND_DO_FCALL_SPEC_RETVAL_UNUSED_HANDLER /tmp/php-asan/Zend/zend_vm_execute.h:1919:4
    #16 0x561f8b1b183d in execute_ex /tmp/php-asan/Zend/zend_vm_execute.h:58565:7
    #17 0x561f8b1b2067 in zend_execute /tmp/php-asan/Zend/zend_vm_execute.h:64217:2
    #18 0x561f8b5e6860 in zend_execute_script /tmp/php-asan/Zend/zend.c:1932:3
    #19 0x561f8ae04d2b in php_execute_script_ex /tmp/php-asan/main/main.c:2574:13
    #20 0x561f8ae05228 in php_execute_script /tmp/php-asan/main/main.c:2614:9
    #21 0x561f8b5ee309 in do_cli /tmp/php-asan/sapi/cli/php_cli.c:935:5
    #22 0x561f8b5eb32c in main /tmp/php-asan/sapi/cli/php_cli.c:1310:18
    #23 0x7f2f8ee29d8f in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:58:16

previously allocated by thread T0 here:
    #0 0x561f8a0879ae in malloc /opt/llvm-15-build/llvm-15.x/final/llvm-project/compiler-rt/lib/asan/asan_malloc_linux.cpp:69:3
    #1 0x561f8b045ce3 in __zend_malloc /tmp/php-asan/Zend/zend_alloc.c:3280:14
    #2 0x561f8b045670 in _emalloc /tmp/php-asan/Zend/zend_alloc.c:2737:10
    #3 0x561f8aa2604f in spl_ptr_llist_push /tmp/php-asan/ext/spl/spl_dllist.c:179:32
    #4 0x561f8aa2fc64 in zim_SplDoublyLinkedList_add /tmp/php-asan/ext/spl/spl_dllist.c:1171:3
    #5 0x561f8b29f2d2 in ZEND_DO_FCALL_SPEC_RETVAL_UNUSED_HANDLER /tmp/php-asan/Zend/zend_vm_execute.h:1919:4
    #6 0x561f8b1b183d in execute_ex /tmp/php-asan/Zend/zend_vm_execute.h:58565:7
    #7 0x561f8b1b2067 in zend_execute /tmp/php-asan/Zend/zend_vm_execute.h:64217:2
    #8 0x561f8b5e6860 in zend_execute_script /tmp/php-asan/Zend/zend.c:1932:3
    #9 0x561f8ae04d2b in php_execute_script_ex /tmp/php-asan/main/main.c:2574:13
    #10 0x561f8ae05228 in php_execute_script /tmp/php-asan/main/main.c:2614:9
    #11 0x561f8b5ee309 in do_cli /tmp/php-asan/sapi/cli/php_cli.c:935:5
    #12 0x561f8b5eb32c in main /tmp/php-asan/sapi/cli/php_cli.c:1310:18
    #13 0x7f2f8ee29d8f in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:58:16

SUMMARY: AddressSanitizer: heap-use-after-free /tmp/php-asan/ext/spl/spl_dllist.c:1014:19 in zim_SplDoublyLinkedList_serialize
Shadow bytes around the buggy address:
  0x0c067fffd4a0: fd fd fa fa fd fd fd fd fa fa fd fd fd fd fa fa
  0x0c067fffd4b0: fd fd fd fd fa fa fd fd fd fd fa fa fd fd fd fd
  0x0c067fffd4c0: fa fa fd fd fd fd fa fa fd fd fd fd fa fa fd fd
  0x0c067fffd4d0: fd fd fa fa 00 00 00 00 fa fa 00 00 00 00 fa fa
  0x0c067fffd4e0: fd fd fd fd fa fa fd fd fd fd fa fa 00 00 00 fa
=>0x0c067fffd4f0: fa fa 00 00 00 fa fa fa 00 00 00 00 fa fa fd[fd]
  0x0c067fffd500: fd fd fa fa 00 00 00 00 fa fa fa fa fa fa fa fa
  0x0c067fffd510: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c067fffd520: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c067fffd530: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c067fffd540: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
Shadow byte legend (one shadow byte represents 8 application bytes):
  Addressable:           00
  Partially addressable: 01 02 03 04 05 06 07 
  Heap left redzone:       fa
  Freed heap region:       fd
  Stack left redzone:      f1
  Stack mid redzone:       f2
  Stack right redzone:     f3
  Stack after return:      f5
  Stack use after scope:   f8
  Global redzone:          f9
  Global init order:       f6
  Poisoned by user:        f7
  Container overflow:      fc
  Array cookie:            ac
  Intra object redzone:    bb
  ASan internal:           fe
  Left alloca redzone:     ca
  Right alloca redzone:    cb
==954815==ABORTING
```

## PHP Version
PHP 8.5.0-dev

## Operating System
No response
