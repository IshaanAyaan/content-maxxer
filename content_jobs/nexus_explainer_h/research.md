# Research Notes: Nexus Explainer H

## Observed from the seed render

- The visual story contrasts average-type scoring with intersection-type agreement.
- It frames pretraining loss as a scorecard, while downstream behavior depends on where optimization lands.
- It uses task-specific "valleys" and loss landscapes as the main analogy.
- It shows an engineering adaptation with a cloned model, mini-batch inner steps, and displacement converted into `g_hat`.

## Visual ingredients to keep

- Input streams flowing into an LLM.
- Two overlapping loss landscapes.
- A curve with a best downstream point.
- A compact implementation diagram.
- A final memory hook.

## Open research items

- Pull exact terminology and figures from the paper.
- Confirm the formal definition of the relational optimizer objective.
- Decide which equations deserve screen time and which should become narration.
- Add a narration script that explains `g_hat` without requiring prior optimizer theory.
