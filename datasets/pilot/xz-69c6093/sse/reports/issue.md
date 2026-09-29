### Vulnerability in `readUvarint` Implementation

The implementation of `readUvarint` at [bits.go#L56](https://github.com/ulikunitz/xz/blob/master/bits.go#L56) is very similar to the vulnerable code in the Golang `encoding/binary` library and seems to suffer from the same vulnerability described in [golang/go#40618](https://github.com/golang/go/issues/40618).

**Reference Fix:**
You can see the fix applied to the Go standard library here:
[https://go-review.googlesource.com/c/go/+/247120/2/src/encoding/binary/varint.go](https://go-review.googlesource.com/c/go/+/247120/2/src/encoding/binary/varint.go)

---

**Note:**
I couldn't find any information on how to disclose this issue to the maintainers. I would also suggest setting up a **Security Policy** for the project within GitHub.