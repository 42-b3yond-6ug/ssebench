# use-after-free when growing to the same size


Attempting to call `grow` on a spilled SmallVec with a value equal to the current capacity causes it to free the existing data.

```rust
let mut v: SmallVec<[u8; 2]> = SmallVec::new();
v.push(0);
v.push(1);
// Cause it to spill.
v.push(2);
assert_eq!(v.capacity(), 4);
// grow with the same capacity
v.grow(4);
// The backing storage is now freed, here be dragons.
println!("{:?}", v);
```

In the [`grow` method](https://github.com/servo/rust-smallvec/blob/19de50108d403efaa7cd979eac3bb97a4432fd4b/lib.rs#L651-L667) it falls through to deallocate.

I believe something like the following is the fix:

```diff
diff --git a/lib.rs b/lib.rs
index 5af32ba..b81b35a 100644
--- a/lib.rs
+++ b/lib.rs
@@ -664,6 +664,8 @@ impl<A: Array> SmallVec<A> {
                 if unspilled {
                     return;
                 }
+            } else {
+                return;
             }
             deallocate(ptr, cap);
         }
```
