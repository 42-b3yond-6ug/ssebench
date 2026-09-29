# Invalid Memory Read in FreeList<wabt::interp::Object*>::IsUsed()

## Environment

```
OS               : Linux 5.15.133.1-microsoft-standard-WSL2 #1 SMP Thu Oct 5 21:02:42 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux
Commit           : 9fdd024249b6b181d98a4164700ca6ee09f970d9 - 1471dffee8bf9939044b80d34256956a28138e96
Version          : 1.0.33 (git~1.0.33-35-gdddc03d3)
Clang Verison    : 13.0.0
Build            : mkdir build && cd build && export CC=clang CXX=clang++ CFLAGS="-fsanitize=address -g" CXXFLAGS="-fsanitize=address -g" && cmake .. && cmake --build .
Affected Tool    : wasm-interp
Enabled Features : None
Impact           : Invalid Memory Read
```

## Proof of Concept

[wasm-poc-03.zip](wasm-poc-03.zip)

## Stack Trace Provide By AddressSanitizer

```
AddressSanitizer:DEADLYSIGNAL
=================================================================
==2716==ERROR: AddressSanitizer: SEGV on unknown address 0x611000081078 (pc 0x00000053636f bp 0x7fff7f323910 sp 0x7fff7f3238f0 T0)
==2716==The signal is caused by a READ memory access.
    #0 0x53636f in wabt::interp::FreeList<wabt::interp::Object*>::IsUsed(unsigned long) const /home/lain/wabt_asan/include/wabt/interp/interp-inl.h:180:39
    #1 0x62e4d6 in wabt::interp::Store::IsValid(wabt::interp::Ref) const /home/lain/wabt_asan/include/wabt/interp/interp-inl.h:482:19
    #2 0x5fdd8f in wabt::interp::Store::HasValueType(wabt::interp::Ref, wabt::Type) const /home/lain/wabt_asan/src/interp/interp.cc:213:8
    #3 0x603cb3 in wabt::interp::Table::Grow(wabt::interp::Store&, unsigned int, wabt::interp::Ref) /home/lain/wabt_asan/src/interp/interp.cc:505:3
    #4 0x626bd2 in wabt::interp::Thread::DoTableGrow(wabt::interp::Instr, wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:2162:21
    #5 0x6185c5 in wabt::interp::Thread::StepInternal(wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:1520:31
    #6 0x60ffbb in wabt::interp::Thread::Run(int, wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:1086:19
    #7 0x602500 in wabt::interp::Thread::Run(wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:1078:14
    #8 0x60173f in wabt::interp::DefinedFunc::DoCall(wabt::interp::Thread&, std::vector<wabt::interp::Value, std::allocator<wabt::interp::Value> > const&, std::vector<wabt::interp::Value, std::allocator<wabt::interp::Value> >&, wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:428:19
    #9 0x600c0d in wabt::interp::Func::Call(wabt::interp::Store&, std::vector<wabt::interp::Value, std::allocator<wabt::interp::Value> > const&, std::vector<wabt::interp::Value, std::allocator<wabt::interp::Value> >&, wabt::interp::RefPtr<wabt::interp::Trap>*, wabt::Stream*) /home/lain/wabt_asan/src/interp/interp.cc:394:10
    #10 0x60dd76 in wabt::interp::Instance::Instantiate(wabt::interp::Store&, wabt::interp::Ref, std::vector<wabt::interp::Ref, std::allocator<wabt::interp::Ref> > const&, wabt::interp::RefPtr<wabt::interp::Trap>*) /home/lain/wabt_asan/src/interp/interp.cc:944:22
    #11 0x526175 in InstantiateModule(std::vector<wabt::interp::Ref, std::allocator<wabt::interp::Ref> >&, wabt::interp::RefPtr<wabt::interp::Module> const&, wabt::interp::RefPtr<wabt::interp::Instance>*) /home/lain/wabt_asan/src/tools/wasm-interp.cc:340:19
    #12 0x51fc12 in ReadAndRunModule(char const*) /home/lain/wabt_asan/src/tools/wasm-interp.cc:423:3
    #13 0x51ecf7 in ProgramMain(int, char**) /home/lain/wabt_asan/src/tools/wasm-interp.cc:450:25
    #14 0x51ff21 in main /home/lain/wabt_asan/src/tools/wasm-interp.cc:456:10
    #15 0x7f1a80556082 in __libc_start_main /build/glibc-SzIz7B/glibc-2.31/csu/../csu/libc-start.c:308:16
    #16 0x43f7ed in _start (/home/lain/wabt_asan/build/wasm-interp+0x43f7ed)

AddressSanitizer can not provide additional info.
SUMMARY: AddressSanitizer: SEGV /home/lain/wabt_asan/include/wabt/interp/interp-inl.h:180:39 in wabt::interp::FreeList<wabt::interp::Object*>::IsUsed(unsigned long) const
==2716==ABORTING
```

