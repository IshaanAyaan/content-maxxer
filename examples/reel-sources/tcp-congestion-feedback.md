# How TCP congestion control learns the available capacity

First, TCP uses a congestion window to limit in-flight data; slow start probes unknown network capacity instead of releasing a large burst.

Each new acknowledgment, or ACK, increases the window, allowing more data in flight while network feedback remains healthy.

At the slow-start threshold, congestion avoidance grows the window gradually, by no more than one maximum-size sender segment per network round trip.

When a retransmission timeout detects loss, TCP sets the threshold to no more than half the data still in flight and reduces the congestion window.

Finally, after recovery the sender tests capacity again with the adjusted window; new ACKs raise it and later congestion lowers it, repeating the feedback loop.

Primary references:

- RFC 5681, sections 2, 3.1, and 3.2: https://www.rfc-editor.org/rfc/rfc5681
- RFC 9293, section 3.8.2: https://www.rfc-editor.org/rfc/rfc9293
