use std::collections::BTreeSet;

fn main() {
    test_base58();
    test_base62();
}

fn test_base58() {
    let mut produced_symbols = BTreeSet::new();

    for _ in 0..100_000 {
        let id = nano_id::base58::<10>();
        for c in id.chars() {
            produced_symbols.insert(c);
        }
    }

    println!(
        "{} symbols generated from nano_id::base58",
        produced_symbols.len()
    );
}

fn test_base62() {
    let mut produced_symbols = BTreeSet::new();

    for _ in 0..100_000 {
        let id = nano_id::base62::<10>();
        for c in id.chars() {
            produced_symbols.insert(c);
        }
    }

    println!(
        "{} symbols generated from nano_id::base62",
        produced_symbols.len()
    );
}
