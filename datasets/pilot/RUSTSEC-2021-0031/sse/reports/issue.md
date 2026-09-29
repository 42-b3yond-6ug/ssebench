# split_at can create unsound aliasing violations if Borrow<Idx> returns different indexes


Hi there, we (Rust group @sslab-gatech) are scanning crates on crates.io for potential soundness bugs. We noticed that in the `split_at` functions:

https://github.com/bennetthardwick/nano-arena/blob/100568c52f47710331ea736ed68070e1aad6cb76/src/lib.rs#L219-L223

`selected.borrow()` is called twice, the first time to select the value from the arena and then the second time to create the split. Since the `Borrow` trait is not required to return the same thing twice, this can be used to create two mutable references to the same object:

```rust
#![forbid(unsafe_code)]

use nano_arena::{Arena, ArenaAccess, Idx};
use std::{borrow::Borrow, cell::Cell};

struct MyIdx {
    idx1: Idx,
    idx2: Idx,
    state: Cell<bool>
}

impl MyIdx {
    fn new(idx1: Idx, idx2: Idx) -> Self {
        MyIdx { idx1, idx2, state: Cell::new(false) }
    }
}

// A borrow implementation that alternatingly returns two different indexes.
impl Borrow<Idx> for MyIdx {
    fn borrow(&self) -> &Idx {
        self.state.set(!self.state.get());
        if (self.state.get()) {
            &self.idx1
        } else {
            &self.idx2
        }
    }
}

fn main() {
    let mut arena = Arena::new();
    let idx1 = arena.alloc(1);
    let idx2 = arena.alloc(2);

    let custom_idx = MyIdx::new(idx1.clone(), idx2.clone());

    let (mutable_ref_one, mut split_arena) = arena.split_at(custom_idx).unwrap();
    let mutable_ref_two : &mut i32 = split_arena.get_mut(&idx1).unwrap();

    println!("{:p} {:p}", mutable_ref_one, mutable_ref_two);
    assert!(mutable_ref_one != mutable_ref_two);
}
```

This outputs:
```
0x55f7f0601ae8 0x55f7f0601ae8
thread 'main' panicked at 'assertion failed: mutable_ref_one != mutable_ref_two', src/main.rs:59:5
```
