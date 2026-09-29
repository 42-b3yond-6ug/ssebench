# push_cloned may drop uninitialized or double-free if clone panics.


Hi there, we (Rust group @sslab-gatech) are scanning crates on crates.io for potential soundness bugs. We noticed a panic safety issue in the `StackA::push_cloned` function:

https://github.com/thepowersgang/stack_dst-rs/blob/807e9d45019c02369e11d40bd181cbf7bb7981fc/src/stack.rs#L153-L161

The `self.push_inner` function increases the length of the stack, but between the element being written and this increased length the `val.clone()` function is called which can leave the stack in a longer state but missing an element. Here's a simple demonstration of this issue:

```rust
#![forbid(unsafe_code)]

use stack_dst::StackA;

#[derive(Debug)]
struct DropDetector(u32);

impl Drop for DropDetector {
    fn drop(&mut self) {
        println!("Dropping {}", self.0);
    }
}

impl Clone for DropDetector {
    fn clone(&self) -> Self { panic!("Panic in clone()") }
}

fn main() {
    let mut stack = StackA::<[DropDetector], [usize; 9]>::new();
    stack.push_stable([DropDetector(1)], |p| p).unwrap();
    stack.push_stable([DropDetector(2)], |p| p).unwrap();

    println!("Popping off second drop detector");
    let second_drop = stack.pop();

    println!("Pushing panicky-clone");
    stack.push_cloned(&[DropDetector(3)]).unwrap();
}
```

This outputs:
```
Popping off second drop detector
Dropping 2
Pushing panicky-clone
thread 'main' panicked at 'Panic in clone()', src/main.rs:29:31
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
Dropping 3
Dropping 2
Dropping 1

Return code 101
```

Notice that `Dropping 2` is printed twice, indicating a double-free.
