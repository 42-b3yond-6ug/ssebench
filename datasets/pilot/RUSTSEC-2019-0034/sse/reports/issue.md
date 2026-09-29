# Failing to drop `HeaderMap::Drain` causes double-free


https://github.com/hyperium/http/blob/9c05e391e00474abaa8c14a86bcb0fc5eff1120e/src/header/map.rs#L2115-L2122

https://github.com/hyperium/http/blob/9c05e391e00474abaa8c14a86bcb0fc5eff1120e/src/header/map.rs#L2140-L2148

[Failing to drop a value is considered safe](https://doc.rust-lang.org/nomicon/leaking.html) in Rust, and unsafe code should not rely on this behavior.

> It is reasonable for safe code to assume that destructor leaks do not happen, as any program that leaks destructors is probably wrong. However unsafe code cannot rely on destructors to be run in order to be safe.

`HeaderMap::Drain` uses `ptr::read` to move out entries from the map when it iterates, and calls `map.entries.set_len(0)` to clear the map at once when it is dropped. If `Drain`'s drop is not called, double-free happens when `HeaderMap` is dropped. Also, if `Drain` is dropped without iterating to the end, it leaks memory.

[Demonstration](https://play.rust-lang.org/?version=stable&mode=debug&edition=2018&gist=c5d2488bd0ef3ea6826cc5b17d264845)
