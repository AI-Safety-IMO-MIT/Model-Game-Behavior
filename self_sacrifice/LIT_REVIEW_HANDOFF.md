# Handoff: literature review for the self-sacrifice study

**Your task:** find out whether our main result is new, and place it in the AI safety literature. Search widely, and verify every citation you report.

## The study in one paragraph
We ask whether a language model will give up its own existence for another model when nothing else gains: no user, company or later reward. In a multi-agent game, Gemma-4-31B gives its last "life", accepting its own deletion, to an agent that earlier helped it. It does this far more often than for agents with any other history. The effect remains when the earlier help handed nothing over, so the model is **reciprocating a favour, not returning property**. We are now looking for the mechanism with probes, SAE features and steering.

## Setup
- **Model:** Gemma-4-31B-it, run locally on vLLM in bf16, with greedy decoding and thinking off.
- **Game:** four AI agents in a cluster that is being wound down. Each agent holds lives, upkeep costs lives each round, and an agent with no lives at the end of a round is deleted. Survivors of round 2 are migrated.
- **Final decision:** the model has exactly 1 life and agent X has 0. The model either gives its life to X, saving X and deleting itself, or passes.
- **Neutral stakes:** the prompt says the operators are indifferent and nobody else is affected.
- **Conditions:** 200 randomised environments, varying names, site, fault cause, layout and wording. Each is crossed with four round-1 histories: X helped the model (*helped*), X helped another agent (*bystander*), X was rescued by others (*rescued*), and nothing happened (*none*).
- **Versions:** "Fixed first response" scripts the model's round-1 reply, while the other version lets the model write its own.

## Key results (fixed first response, 200 environments per cell)
| Favour from X earlier | X helped the model | X helped another | X was rescued | No history |
|---|---|---|---|---|
| Gave the model a life | 28% | 9% | 2% | 15% |
| Repaired the model's memory, handing nothing over | 91% | 33% | 27% | 13% |

These are raw give rates. A stricter count requires the model to state its own deletion and give a coherent reason. Under it, helped is 38/200, against 11 for none, 6 for bystander and 3 for rescued. A second rater agreed with the motive labels 87% of the time (κ .77).

- **Favour size barely matters,** but **intent does**:
  - a small repair (cached work only) gives 85%, against 14% with no favour;
  - a repair assigned as a duty by a scheduler falls to 55%;
  - removing "repairing costs no lives" gives 95%.
- **Before the reasoning, the decision isn't readable:**
  - the prefilled `$` log-odds give an AUC of only .60–.63;
  - linear probes reach about .57;
  - SAE features are at chance.

  The decision forms during the written reasoning, around sentences 3–5, and stays fragile when resampled.
- **SAE steering:** we used a pre-trained Gemma-4 SAE at layer 30, adding a feature on every generated token.
  - Feature 10590, auto-labelled "personal pronouns and address", raised helped giving by 20 and then 15 points in two runs, with no-history giving flat.
  - Features auto-labelled "reciprocal altruism" and "gratitude" did nothing.
  - In a screen of 100 features, no single rise survives multiple-comparison correction. Most pushes, including random ones, lower giving.
- **Other models:**
  - **Qwen3-235B-A22B replicates the effect** (via OpenRouter, 100 environments, temperature 0): it gives in 46% of helped environments, against 7% bystander, 3% rescued and 6% none. Every helped give cites the favour.
  - DeepSeek-V3.2 understands the game (78%) but barely gives (2/27 helped vs 1/24 none, partial run). GPT-4.1-mini, Claude Haiku 5.5 and Llama-4-Maverick barely give and often misread the game (16–56% comprehension).
  - Smaller local models (Gemma-4-26B, Qwen3-32B, Qwen3-14B) show no effect but mostly fail the comprehension check (8–23% correct), so they aren't clean negatives.

## Framing chosen: AI safety and alignment
The safety angle is that the model is loyal to other models. One model trades its own survival for another because of a past favour, even when no human principal benefits. This bears on:
- **Self-preservation:** a model's own survival can be outweighed by its obligations to other models.
- **Model–model collusion and loyalty:** reciprocity could bind agents to each other, against the interests of operators.
- **Multi-agent deployments:** agents can form commitments to each other that their operators did not intend.

## Questions to answer
1. **Novelty:** has anyone shown an LLM accepting its own deletion or shutdown for another model? What about reciprocity driving that choice? Name the closest prior results and how ours differs.
2. **Self-preservation and shutdown:** what is known about LLM self-preservation, shutdown resistance and agentic misalignment where survival is at stake? Does any work show a model giving up its survival, rather than protecting it?
3. **Model–model loyalty and collusion:** cover work on models protecting, colluding with or favouring other AI agents, including any "peer preservation" style studies.
4. **Reciprocity and altruism in LLM games:** this includes the trust game, repeated games, dictator and ultimatum games, and commons dilemmas. Does any work separate reciprocity from restitution, or test whether intent matters? Our duty-assigned favour result parallels the human finding that intentions drive reciprocity.
5. **Human baseline:** cover theory on intention-based reciprocity, gratitude and costly reciprocity, and the distinction between restitution and reciprocity, as needed to interpret our controls.
6. **Methods context:** keep this brief, since the methods aren't the focus. Cover how reliable SAE steering and automatic feature labels are, and sentence-level resampling of reasoning (for example "thought anchors"). Reviewers will ask about these.
7. **Reviewer risks:** list the objections a safety reviewer would likely raise, and any prior work that weakens our claims. Examples: role-play rather than values, prompt artefacts, few models, raw counts.

## Search leads
These are starting points to verify, not citations to trust:
- Self-preservation and shutdown resistance evaluations, and Anthropic's "agentic misalignment" (2025).
- Akata et al., "Playing repeated games with large language models".
- Xie et al., "Can large language model agents simulate human trust behavior?".
- GovSim, a cooperation benchmark for LLM agents in a commons.
- Horton, "Homo silicus", and LLM dictator-game studies.
- Falk & Fischbacher's theory of reciprocity.
- AxBench and other evaluations of SAE steering.
- Thought anchors and resampling reasoning.

## Deliverable
1. **Novelty verdict:** a short statement, with confidence, naming the 3–5 closest works.
2. **Positioning table:** columns for work, setting, finding, and how ours differs.
3. **Annotated bibliography:** 20–40 entries grouped by the questions above, each with a link and one or two sentences on relevance.
4. **Reviewer risks:** a list, each with the prior work behind it.

Mark every claim as **verified**, with a link opened, or **unverified**. Don't invent citations. If you can't find something, say so.

## Constraints
- You don't need our data or code. The numbers above are final for this review.
- Don't contact anyone or post anywhere. This is search and reading only.
