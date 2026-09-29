Reported by [@Ry0taK](https://github.com/Ry0taK) at 2021-03-27T01:00

I'm a security researcher who has been fuzzing famous XSS sanitizers.

While fuzzing the sanitizers, my fuzzer triggered an alert that shows bluemonday is vulnerable to bypass.
After some checks, I confirmed that this is a vulnerability, so I'm reporting it here.

While checking the issues on the bluemonday repository, I realized that this is the same issue as [#56](https://github.com/microcosm-cc/bluemonday/issues/56) (Which must be resolved already as it's closed.)
As there is no doubt this vulnerability occurred again in somewhere of previous commits, I decided to find it.
And it was a commit that added vulnerable code again: [876b478#diff-c62e8d687f2dd220893e9990667b682f3261099565c254e3d236178f07729920](https://github.com/microcosm-cc/bluemonday/commit/876b4780bed1f83d4556865fead6765d72178ca7#diff-c62e8d687f2dd220893e9990667b682f3261099565c254e3d236178f07729920)

(It's now moved to here:

[bluemonday/sanitize.go](https://github.com/microcosm-cc/bluemonday/blob/22ed3129fd968e326c5c15faef11b72dd7e65c95/sanitize.go#L232)

Line 232 in [22ed312](https://github.com/microcosm-cc/bluemonday/commit/22ed3129fd968e326c5c15faef11b72dd7e65c95)

```go
mostRecentlyStartedToken = strings.ToLower(token.Data)
```

To reproduce this, please use the following steps:

1.  Download the attached bluemonday.zip
    
2.  Extract it.
    
3.  Run test.go: "go run test.go"
    
4.  Sanitization bypass will be shown.
    

If you are going to fix this issue, please let me know. I can assign CVE to notify this issue to users.

Best regards, RyotaK



