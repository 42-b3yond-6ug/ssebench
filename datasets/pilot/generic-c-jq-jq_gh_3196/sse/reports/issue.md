# Stack-buffer-overflow in decNumberCopy Function in jq 1.7.1

## Description

An AddressSanitizer error has been detected in jq version 1.7.1, indicating a stack-buffer-overflow in the decNumberCopy function within decNumber.c. This issue was uncovered during fuzz testing and may lead to undefined behavior, crashes, or potential security vulnerabilities.

## AddressSanitizer Report

```
==11784==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7f659bc00570 at pc 0x556a4b26bac8 bp 0x7ffc7d681f50 sp 0x7ffc7d681f48
WRITE of size 2 at 0x7f659bc00570 thread T0
    #0 0x556a4b26bac7 in decNumberCopy /src/jq/src/decNumber/decNumber.c:3375:45
    #1 0x556a4b26bac7 in decNaNs /src/jq/src/decNumber/decNumber.c:7706:33
    #2 0x556a4b25d318 in decCompareOp /src/jq/src/decNumber/decNumber.c:6085:7
    #3 0x556a4b25cfa2 in decNumberCompare /src/jq/src/decNumber/decNumber.c:858:3
    #4 0x556a4b2202a0 in jvp_number_cmp /src/jq/src/jv.c:748:5
    #5 0x556a4b2227ee in jvp_number_equal /src/jq/src/jv.c:773:10
    #6 0x556a4b2227ee in jv_equal /src/jq/src/jv.c:1916:11
    #7 0x556a4b2230c1 in jvp_array_equal /src/jq/src/jv.c:885:10
    #8 0x556a4b2230c1 in jv_equal /src/jq/src/jv.c:1919:11
    #9 0x556a4b23019c in jv_group /src/jq/src/jv_aux.c:714:11
    #10 0x556a4b29890b in f_group_by_impl /src/jq/src/builtin.c:842:12
    #11 0x556a4b217653 in jq_next /src/jq/src/execute.c:921:21
    #12 0x556a4b20afae in LLVMFuzzerTestOneInput /src/jq/./tests/jq_fuzz_fixed.cpp:283:23
    #13 0x556a4b0bf740 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerLoop.cpp:614:13
    #14 0x556a4b0aa9b5 in fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:327:6
    #15 0x556a4b0b044f in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:862:9
    #16 0x556a4b0db6f2 in main /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerMain.cpp:20:10
    #17 0x7f659e3de082 in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x24082)
    #18 0x556a4b0a2b9d in _start (/out/jq_fuzz_fixed+0xddb9d)

Address 0x7f659bc00570 is located in stack of thread T0 at offset 48 in frame
    #0 0x556a4b22010f in jvp_number_cmp /src/jq/src/jv.c:737

  This frame has 1 object(s):
    [32, 48) 'res' (line 743) <== Memory access at offset 48 overflows this variable
HINT: this may be a false positive if your program uses some custom stack unwind mechanism, swapcontext or vfork
      (longjmp and C++ exceptions *are* supported)
```

## Environment
- jq Version: 1.7.1
- Build Configuration: OSS-Fuzz

## Reproduce
```
echo -n WzYsbmFuNjAwMDAwMDAwNV1cIDdcIOQ= | base64 -d > poc
./jq_fuzz_fixed poc
```
