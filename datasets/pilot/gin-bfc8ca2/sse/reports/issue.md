[gin/context.go](https://github.com/gin-gonic/gin/blob/b94d23d1b48d7b5078035ddbab0c3b5df138b827/context.go#L716-L725)

Lines 716 to 725 in [b94d23d](https://github.com/gin-gonic/gin/commit/b94d23d1b48d7b5078035ddbab0c3b5df138b827)

|     | if c.engine.ForwardedByClientIP { |
| --- | --- |
|     | clientIP := c.requestHeader("X-Forwarded-For") |
|     | clientIP \= strings.TrimSpace(strings.Split(clientIP, ",")\[0\]) |
|     | if clientIP \== "" { |
|     | clientIP \= strings.TrimSpace(c.requestHeader("X-Real-Ip")) |
|     | }   |
|     | if clientIP != "" { |
|     | return clientIP |
|     | }   |
|     | }   |

If Gin is exposed directly to the internet, a client can easily spoof its client IP by simply setting an X-Forwarded-For header.

The correct way to handle this is to require a list of trusted proxies to be configured. If unset, X-Forwarded-For should be ignored.

I filed a similar issue against Cloud Foundry's gorouter a few years ago. [cloudfoundry/gorouter#179](https://github.com/cloudfoundry/gorouter/issues/179) In case that repo should migrate elsewhere, I'm copying the contents of the report in its entirety here:

## Issue

X-Forwarded-For is passed through unfiltered, allowing anyone to spoof their origin IP.

## Context

X-Forwarded-For records the path a given request has taken. The first IP is the origin client, each subsequent IP denotes a path along the way (proxies, load balancers, whatever). It's the only way for a backend service to determine the original IP, since the incoming connection is from the gorouter.

However, blindly trusting the header obviously allows anyone to spoof the origin IP. Common ways to address this security problem is to only trust X-Forwarded-For headers from trusted sources.

Examples of how to mitigate this problem:  
[https://httpd.apache.org/docs/current/mod/mod\_remoteip.html#remoteiptrustedproxy](https://httpd.apache.org/docs/current/mod/mod_remoteip.html#remoteiptrustedproxy)  
[http://nginx.org/en/docs/http/ngx\_http\_realip\_module.html#set\_real\_ip\_from](http://nginx.org/en/docs/http/ngx_http_realip_module.html#set_real_ip_from)

## Steps to Reproduce

Pass a X-Forwarded-For header with someone else's IP (e.g. 8.8.8.8) in it to your application, and it'll appear as though that's where the request came from.

## Expected result

Since I'm not a trusted client, my X-Forwarded-For header should have been discarded, and my IP should be the first in the X-Forwarded-For header received by the backend.

## Current result

The backend service will see an X-Forwarded-For header reading "8.8.8.8, [my real IP], [gorouter IP]" (possibly more, if there's a load balancer or something in the path). It will think the request came from 8.8.8.8.

## Possible Fix

Allow specifying a list of IPs (or CIDR's) of trusted proxies and load balancers. If the request didn't come from one of them, discard the X-Forwarded-For. For bonus points, do what nginx does: Go through the list (starting from the last entry) and check each entry to see if it's the list of trusted proxies. When one is encountered that's not on the list, discard everything before it.

All of the above also applies to X-Forwarded-Proto. We shouldn't trust people to say that their request was ever HTTPS if it never was.

React👍React with 👍1bokwoon95