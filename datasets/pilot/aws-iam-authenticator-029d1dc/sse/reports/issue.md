CVSS Rating: [High](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N)

A security issue was discovered in aws-iam-authenticator where an allow-listed IAM identity may be able to modify their username and escalate privileges.

This issue has been rated **high** ([https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N)), and assigned [CVE-2022-2385](https://github.com/advisories/GHSA-pp3f-98qg-5g75 "CVE-2022-2385")

### Am I vulnerable?

Users are only affected if they use the AccessKeyID template parameter to construct a username and provide different levels of access based on the username.

### Detection

This issue affected the logged identity, and is not discernible from valid requests.

#### Acknowledgements

This vulnerability was reported by Gafnit Amiga from Lightspin.

/area security
/kind bug
/committee security-response
/label official-cve-feed
