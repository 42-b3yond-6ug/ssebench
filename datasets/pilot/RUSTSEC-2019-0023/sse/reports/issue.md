# Unsoundness (use after free) around `StringInterner::clone()` and `InternalStrRef`


# Abstract
By steps below, call to `StringInterner::get_or_intern()` and `StringInterner::get()` cause **use after free** in `string-interner 0.7.0`.

1. Create a `StringInterner`. I'll call it `old`.
2. Intern some string.
2. Clone `old`. I'll call the newly created interner `old`.
    + `let new = old.clone();`.
3. Drop `old`.
    + At this point, all `Box<str>`s in `old.values` is also going to be dropped.
4. Call `new.get_or_intern()` or `new.get()`, passing same string as before.
    + These functions refer `Box<str>` strings already dropped. This is UB.

# Code to reproduce
```rust
// `string-interner = "=0.7.0"` in Cargo.toml.
use string_interner::{DefaultStringInterner, Sym};

fn clone_and_drop() -> (DefaultStringInterner, Sym) {
    let mut old = DefaultStringInterner::new();
    let foo = old.get_or_intern("foo");

    let new = old.clone();
    let _bar = old.get_or_intern("bar");

    (new, foo)
}

fn main() {
    let (mut new, foo) = clone_and_drop();
    assert_eq!(
        new.get_or_intern("foo"),
        foo,
        "`foo` should represent the string \"foo\" so they should be equal"
    );
}
```

```
$ cargo run
   Compiling string-interner-unsoundness-test v0.1.0 (/home/lo48576/works/public/playground/rust/string-interner-unsoundness-test)
    Finished dev [unoptimized + debuginfo] target(s) in 0.33s
     Running `target/debug/string-interner-unsoundness-test`
thread 'main' panicked at 'assertion failed: `(left == right)`
  left: `Sym(2)`,
 right: `Sym(1)`: `foo` should represent the string "foo" so they should be equal', src/main.rs:15:5
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace.
$
```

The last `assert_eq!` should never fail, but it failed in my environment.
(This is UB so it might success coincidentally...)

See  <https://github.com/lo48576/string-interner/blob/5bb5485c8479b2bfb40d83758c0db56f8f466efe/TEST_RESULT.md> for more detailed explanation.
