# How self-attention builds context

In the Transformer, each token is projected into a query, a key, and a value representation.

Attention scores compare a token’s query with other tokens’ keys, commonly using a scaled dot product.

A softmax converts those scores into normalized weights that determine how strongly the token uses each value.

The weighted values are combined, allowing the representation of a token to incorporate information from other positions in the sequence.

Multi-head attention performs several attention operations in parallel, allowing different heads to represent different relationships.

Because self-attention by itself does not encode token order, the original Transformer adds positional information to the input representations.

Primary reference: Vaswani et al., “Attention Is All You Need,” sections 3.2 and 3.5.

https://arxiv.org/abs/1706.03762
