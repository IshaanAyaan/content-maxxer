# Slide Storyboard: How Large Language Models Work

| # | Role | Headline | Visual | Body |
| ---: | --- | --- | --- | --- |
| 1 | hook | It is not reading words. | token_split | A language model turns text into tiny IDs, then learns what should come next. |
| 2 | map | Text goes in. One token comes out. | pipeline | Everything else is the machinery that makes that next-token guess smarter. |
| 3 | mechanism | Text becomes tokens. | token_cards | Tokens are chunks the model can count. Some are words. Some are pieces. |
| 4 | mechanism | Tokens become vectors. | vector_space | Each token becomes a point in a learned space where meaning can be compared. |
| 5 | mechanism | Attention decides what matters. | attention_arcs | Every token looks at the other tokens and borrows the context it needs. |
| 6 | mechanism | Layers refine the guess. | layer_stack | Transformer blocks keep mixing and reshaping the vectors until the next token is clearer. |
| 7 | payoff | It picks a next token. | probability_bars | The model scores many possible next tokens, then samples one from the distribution. |
| 8 | takeaway | LLMs are next-token engines. | loop | The magic is not one giant answer. It is a tiny prediction loop repeated very fast. |
