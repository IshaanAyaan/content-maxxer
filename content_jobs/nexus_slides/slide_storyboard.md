# Slide Storyboard: Nexus

| # | Role | Headline | Visual | Body |
| ---: | --- | --- | --- | --- |
| 1 | hook | Same loss. Different model. | basins | Two models can tie on pretraining loss and still land in different downstream regions. |
| 2 | problem | Loss is a scoreboard. | score_vs_route | A scoreboard tells you the number. It does not tell you where training landed. |
| 3 | mechanism | Downstream tasks live in valleys. | downstream_valley | If a model lands near useful downstream valleys, adaptation gets easier. |
| 4 | mechanism | Do tasks pull together? | task_arrows | Nexus asks whether task directions agree or fight with each other during training. |
| 5 | mechanism | Clone. Step. Measure. | inner_loop | Temporary inner steps estimate how training moves the model under task batches. |
| 6 | takeaway | Nexus changes the route. | route_takeaway | The paper is about shaping the training path, not just lowering one final score. |
