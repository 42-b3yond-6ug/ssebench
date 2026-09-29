# Unable to generate the correct character set

# Reduced entropy due to inadequate character set usage

## Description

Affected versions of the nano-id crate incorrectly generated IDs using a reduced character set in the nano_id::base62 and nano_id::base58 functions. Specifically, the base62 function used a character set of 32 symbols instead of the intended 62 symbols, and the base58 function used a character set of 16 symbols instead of the intended 58 symbols. Additionally, the nano_id::gen macro is also affected when a custom character set that is not a power of 2 in size is specified.

It should be noted that nano_id::base64 is not affected by this vulnerability.

## Impact

This can result in a significant reduction in entropy, making the generated IDs predictable and vulnerable to brute-force attacks when the IDs are used in security-sensitive contexts such as session tokens or unique identifiers.

## PoC

use std :: collections :: BTreeSet ; fn main ( ) { test_base58 ( ) ; test_base62 ( ) ; } fn test_base58 ( ) { let mut produced_symbols = BTreeSet :: new ( ) ; for _ in 0 .. 100_000 { let id = nano_id :: base58 :: < 10 > ( ) ; for c in id . chars ( ) { produced_symbols . insert ( c ) ; } } println ! ( "{} symbols generated from nano_id::base58" , produced_symbols . len ( ) ) ; } fn test_base62 ( ) { let mut produced_symbols = BTreeSet :: new ( ) ; for _ in 0 .. 100_000 { let id = nano_id :: base62 :: < 10 > ( ) ; for c in id . chars ( ) { produced_symbols . insert ( c ) ; } } println ! ( "{} symbols generated from nano_id::base62" , produced_symbols . len ( ) ) ; }

