# xxd: buffer-overflow with specific flags

xxd writes each output line into a global buffer before printing. The maximum size of that buffer was not calculated correctly.

This command was crashing in AddressSanitizer:

```
xxd -Ralways -g1 -c256 -d -o 9223372036854775808 /etc/passwd
```

This prints a line of 6680 bytes but the buffer only had room for 6549 bytes. If the output from "-b" was colored, the line could be even longer.
