**What would you like to be added**:

Remove all the unnecessary RBAC permission in the helm charts.

[#1105](https://github.com/submariner-io/submariner-operator/issues/1105) may relate to this.

**Why is this needed**:

Unnecessary rbac permissions can lead to security risks. Currently, the submariner-operator's helm charts have applied for too many permissions it doesn’t need, such as Deployment `submariner-operator`. Among them, we found that several sensitive permissions may even lead to the hijacking of the cluster under specific attacks. Due to the risk of security disclosure, we have hidden the details of these permissions in the public issue. We have reported this security issue through private email and received confirmation from the community.