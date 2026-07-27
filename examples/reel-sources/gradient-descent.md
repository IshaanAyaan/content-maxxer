# How gradient descent learns

A machine-learning model’s loss function assigns a number to how wrong its current predictions are.

The gradient points in the direction of the steepest local increase in that loss, so gradient descent updates parameters in the opposite direction.

Each update moves the model to a new point on the loss surface, where the gradient is calculated again.

The learning rate controls the size of each step: a very small rate can make learning slow, while a rate that is too large can overshoot a useful minimum.

Repeating these updates can move the parameters toward a region with lower loss, although the surface may contain flat areas, saddle points, or multiple minima.

Primary reference: Stanford CS231n, “Optimization.”

https://cs231n.github.io/optimization-1/
