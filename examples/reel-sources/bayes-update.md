# Why two heads make the trick coin more likely

Before either coin is tossed, suppose a fair coin and a trick coin that always lands heads are equally likely, so each hypothesis starts with prior probability one half.

Seeing two heads has likelihood one quarter if the coin is fair, because two independent fair tosses must both land heads, but likelihood one if the coin is the trick coin.

Bayes' theorem updates each hypothesis by multiplying its prior probability by the likelihood of the observed evidence under that hypothesis.

The unnormalized weights are one eighth for the fair coin and one half for the trick coin; normalizing those weights gives posterior probability one fifth for fair and four fifths for trick.

The evidence does not simply replace the prior: it reweights the competing hypotheses, producing a posterior probability after the two heads are observed.

Primary references:

- David Aldous and Janko Gravner, *Lecture Notes for Introductory Probability*, Theorem 4.2 and Example 4.9: https://www.stat.berkeley.edu/~aldous/134/gravner.pdf
- OpenStax, *Principles of Data Science*, Section 3.4 Probability Theory: https://openstax.org/books/principles-data-science/pages/3-4-probability-theory
