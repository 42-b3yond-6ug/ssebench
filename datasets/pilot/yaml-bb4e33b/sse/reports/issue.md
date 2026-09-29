### Summary

The YAML decoder has no protection against alias expansion bombs, allowing a small YAML document to expand into billions of decoded nodes and consume all available memory during unmarshalling.

### Root Cause

YAML anchors (`&name`) and aliases (`*name`) allow defining a value once and referencing it multiple times. The decoder recursively expands each alias reference, duplicating all the nodes of the anchored value. Without any limit on expansion, an attacker can chain anchors and aliases exponentially:

```yaml
a: &a ["lol","lol","lol","lol","lol","lol","lol","lol","lol"]
b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]
c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]
...
```

Each level multiplies the number of decoded nodes by 9. With 8 levels of chained aliases, a document under 500 bytes expands to 9^8 ≈ 43 million leaf nodes, each requiring memory allocation during the `unmarshal` call. The decoder's `unmarshal` function processes every expanded node with no mechanism to detect or limit the ratio of alias-driven decodes to direct decodes.

In the `decoder.alias` method, when an alias node is encountered, it calls `d.unmarshal(n.alias, out)` to recursively decode the referenced subtree. There is no tracking of how many decode operations are caused by alias expansion versus direct content, so a document that is mostly alias references triggers unbounded recursive expansion.

### Trigger Conditions

- The application parses untrusted YAML input using `yaml.Unmarshal` or `yaml.Decoder`
- The input contains chained anchor/alias definitions where each level references the previous anchor multiple times
- No external size or depth limits are enforced on the YAML input before parsing

### Impact

An attacker who can submit YAML documents for parsing can crash the application with an out-of-memory panic. A document under 500 bytes can cause the decoder to allocate hundreds of megabytes to gigabytes of memory, leading to denial of service. This is particularly dangerous in server applications that accept YAML configuration or data from untrusted sources.
