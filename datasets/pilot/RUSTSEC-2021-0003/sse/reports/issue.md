# Buffer overflow in `insert_many()`


Hello fellow Rustacean,
we (Rust group @sslab-gatech) found a memory-safety/soundness issue in this crate while scanning Rust code on crates.io for potential vulnerabilities.

## Issue Description

https://github.com/servo/rust-smallvec/blob/9cf11764363d0a349406db752b3315168409562f/src/lib.rs#L1009-L1070

`insert_many()` overflows the buffer when an iterator yields more items than the lower bound of `size_hint()`.

The problem is in line 1044. `reserve(n)` reserves capacity for `n` more elements to be inserted. This is done by comparing the length and the capacity. Since the length of the buffer is set to 0 in line 1032, line 1044 will be always no-op and the following code will overflow the buffer.

## Reproduction

Below is an example program that exhibits undefined behavior using safe APIs of `smallvec`.

```rust
#![forbid(unsafe_code)]

use smallvec::SmallVec;

fn main() {
    let mut v: SmallVec<[u8; 0]> = SmallVec::new();

    // Spill on heap
    v.push(123);

    // Allocate string on heap
    let s = String::from("Hello!");
    println!("{}", s);

    // Prepare an iterator with small lower bound
    let mut iter = (0u8..=255).filter(|n| n % 2 == 0);
    assert_eq!(iter.size_hint().0, 0);

    // Triggering the bug
    v.insert_many(0, iter);

    // Uh oh, heap overflow made smallvec and string to overlap
    assert!(v.as_ptr_range().contains(&s.as_ptr()));

    // String is corrupted
    println!("{}", s);
}
```

Output:
```
Hello!
@BDFHJ
double free or corruption (out)

Terminated with signal 6 (SIGABRT)
```

### Tested Environment

* Crate: smallvec
* Version: 1.6.0
* OS: Ubuntu 20.04.1 LTS
* Rustc version: rustc 1.48.0 (7eac88abb 2020-11-16)
