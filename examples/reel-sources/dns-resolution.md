# How DNS resolution finds an IP address

First, a resolver checks locally available information, including cached records, and returns a usable answer immediately when one is present.

If the resolver has no local answer, it finds the best name servers to ask and sends a DNS query to one of them.

When a response contains a valid referral, the referral points the resolver toward a closer name server, so the resolver updates its server list and repeats the search.

An authoritative answer returns the requested resource data, such as the host address associated with a domain name.

Finally, the resolver returns the answer to the client and stores cacheable response data for future use according to its time to live.

Primary reference: RFC 1034, sections 2.3, 2.4, and 5.3.3.

https://www.rfc-editor.org/rfc/rfc1034
