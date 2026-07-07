# Script: Nexus Explainer H

## Hook

Two models can earn the same pretraining score and still end up in very different places.

## Setup

Think of training as moving through a landscape. The score tells you the height, but not which valley you landed in.

## Mechanism

Nexus cares about whether task valleys agree. If different tasks pull the model toward compatible directions, downstream generalization is more likely.

## Engineering detail

Instead of guessing that agreement directly, Nexus uses a temporary inner model: clone, step on batches, measure the displacement, and turn that motion into a gradient-like signal.

## Takeaway

Pretraining loss is a scorecard. Nexus changes the route through the landscape.
