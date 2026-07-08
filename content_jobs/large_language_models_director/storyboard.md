# Storyboard: How Large Language Models Work

| Scene | Duration | Visual object | Motion | Meaning | Visible text |
| --- | ---: | --- | --- | --- | --- |
| tokens_not_words | 4.6s | a sentence splitting into token cards | A sentence separates into small token cards. | The model sees token IDs, not raw English paragraphs. | text, tokens |
| tokens_to_vectors | 4.6s | token cards becoming vector bars | Each token card drops into a small vector of numbers. | Meaning becomes position in a learned numerical space. | token, vector |
| attention_reads_context | 4.6s | one token sending attention arrows to nearby tokens | Arrows connect the current token to the tokens that change its meaning. | Attention lets a token borrow context from the rest of the sentence. | query, context |
| transformer_layers | 4.6s | vectors passing through attention and MLP blocks | The same vectors pass through repeated transformer layers. | Layers mix context, transform features, and refine the representation. | attention, MLP, repeat |
| predict_next_token | 4.6s | a probability distribution over next-token choices | A bar chart appears with one token getting the highest probability. | The immediate job is next-token prediction. | next token, probability |
| autoregressive_loop | 4.6s | new tokens appended into a growing sentence | The predicted token joins the prompt, then the loop repeats. | Long answers come from repeating the same prediction loop. | predict, append, repeat |
