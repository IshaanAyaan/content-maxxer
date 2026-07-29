# How a TLS 1.3 handshake creates a secure channel

In a TLS 1.3 handshake, the client starts with a ClientHello that offers supported protocol parameters and includes a key share for establishing fresh keying material.

In TLS 1.3, the server answers with a ServerHello and its own key share, and both peers use the exchanged values to derive the same handshake traffic secrets without sending those secrets across the network.

The TLS 1.3 server then sends encrypted handshake messages that select parameters and normally authenticate the server with a certificate and a CertificateVerify signature.

Each TLS 1.3 peer sends a Finished message that authenticates the handshake transcript and the computed keys; an incorrect Finished value makes the peer terminate the connection.

After both sides finish the TLS 1.3 handshake and validate Finished, they can protect application data with the established traffic keys.

Primary reference: RFC 8446, sections 2, 4.1, 4.4, and 7.

https://www.rfc-editor.org/rfc/rfc8446
