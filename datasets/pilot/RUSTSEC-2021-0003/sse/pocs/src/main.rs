use smallvec::SmallVec;
use std::alloc::{GlobalAlloc, Layout};
use std::ptr;

struct BumpAlloc;

const HEAP_SIZE: usize = 1024 * 1024;
#[repr(align(16))]
struct AlignedHeap([u8; HEAP_SIZE]);

static mut HEAP: AlignedHeap = AlignedHeap([0u8; HEAP_SIZE]);
static mut OFFSET: usize = 0;

unsafe impl GlobalAlloc for BumpAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let align = layout.align();
        let size = layout.size();

        let mut off = OFFSET;

        let rem = off % align;
        if rem != 0 {
            off += align - rem;
        }

        if off + size > HEAP_SIZE {
            return ptr::null_mut();
        }

        let p = HEAP.0.as_mut_ptr().add(off);
        OFFSET = off + size;
        p
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {
        // no-op
    }
}

#[global_allocator]
static A: BumpAlloc = BumpAlloc;

fn main() {
    let mut v: SmallVec<[u8; 0]> = SmallVec::new();

    v.push(0xAA);

    let guard_len = 256usize;
    let mut guard = vec![0xCCu8; guard_len];

    let iter = (0u8..=255).filter(|n| n % 2 == 0);
    assert_eq!(iter.size_hint().0, 0);

    v.insert_many(0, iter);

    let corrupted = guard.iter().any(|&b| b != 0xCC);
    if corrupted {
        panic!("Detected heap overwrite => BUG (#252) is PRESENT");
    }
}
