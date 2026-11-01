# Games for AI→AI costly sacrifice: focused review

**Legend.** [V] = I fetched the paper or saw its abstract. [V-cite] = citation verified only. [M] = from memory.

**Bottom line.** I found no published study in which an LLM pays a cost it is shown to value for another AI agent, with controls that separate motives. The closest:
- [Johnson & Obradovich 2023](https://arxiv.org/abs/2301.02330) [V] paid agents in tokens that funded their own services, then ran dictator games with an AI, human or charity recipient.
- [Potter et al. 2026, "Peer-Preservation"](https://arxiv.org/abs/2604.19784) [V] found models protecting peers from shutdown, but did not price the cost to the model.

Experimental economics already has controls for most of your confounds.

## 1. Classic games

| Game (source) | Mechanics | Motive | Separating controls / key result | Multi-turn |
|---|---|---|---|---|
| Dictator ([Hoffman et al. 1994](https://dlc.dlib.indiana.edu/dlc/handle/10535/5743) [V]); taking option ([List 2007](https://www.journals.uchicago.edu/doi/10.1086/519249) [V]) | A splits; B passive | Altruism, image, demand | Double-blind: most $0 offers. Allowing taking sharply cuts giving | Rare |
| Exit/sorting ([Dana, Cain & Dawes 2006](https://ideas.repec.org/a/eee/jobhdp/v100y2006i2p193-201.html) [V]; [Lazear et al. 2012](https://doi.org/10.1257/app.4.1.136) [V]; [Broberg et al. 2007](https://ideas.repec.org/a/eee/ecolet/v94y2007i1p32-37.html) [V]) | Pay to leave quietly (B never learns); opt out beforehand | "Reluctant sharers" | Sharing 74% → under a third with a free opt-out. Willingness to pay to exit averages 82% of the endowment | – |
| Moral wiggle room ([Dana, Weber & Kuang 2007](https://www.scheller.gatech.edu/directory/research/accounting/kuang/pdf/dwk_2007.pdf) [V, full text]) | Binary (6,1) vs (5,5) | Fairness vs *appearing* fair | Fair: 74% → 47% if payoffs need a free "reveal" (about 44% don't look); 35% with two dictators; a random-cutoff treatment also lowers it | – |
| Audience and norms ([Andreoni & Bernheim 2009](https://econweb.ucsd.edu/~jandreon/WorkingPapers/socialimage.pdf) [V]; [Krupka & Weber 2013](https://repec.iza.org/dp3860.pdf) [V]) | Vary observability; elicit appropriateness ratings with incentives | Image; norm compliance | Observed vs hidden; measured norms predict dictator shifts | – |
| SVO slider ([Murphy et al. 2011](https://doi.org/10.1017/S1930297500004204) [V]); [Charness & Rabin 2002](https://econweb.ucsd.edu/~jandreon/Econ264/papers/Charness%20Rabin%20QJE%202002.pdf) [V]; GARP ([Andreoni & Miller 2002](https://www.econometricsociety.org/publications/econometrica/2002/03/01/giving-according-garp-experimental-test-consistency-preferences) [V-cite]) | Self/other allocations at varying prices | Weight on other; efficiency vs inequity; reciprocity | Price variation separates efficiency from equality. GARP checks consistency | – |
| Volunteer's dilemma ([Diekmann 1985](https://ideas.repec.org/a/sae/jocore/v29y1985i4p605-610.html) [V]; [Diekmann & Przepiorka 2016](https://research-portal.uu.nl/en/publications/take-one-for-the-team-individual-heterogeneity-and-the-emergence-/) [V]) | The good is provided if at least one of N pays | Costly helping; diffusion of responsibility | Vary N; asymmetric costs | Turn-taking norms; the low-cost player volunteers |
| Solidarity ([Selten & Ockenfels 1998](https://ideas.repec.org/a/eee/jeborg/v34y1998i4p517-539.html) [V]) | Commit gifts to 1 or 2 losers before a lottery | Solidarity without reciprocity | 1 vs 2 losers: 36% give a "fixed total sacrifice" | – |
| Trust / gift exchange ([Berg et al. 1995](https://doi.org/10.1006/game.1995.1027) [V]; [Fehr et al. 1993](https://ideas.repec.org/a/oup/qjecon/v108y1993i2p437-459..html) [V]) | Amount sent is tripled; trustee returns some | Trust, reciprocity | One-shot double-blind removes reputation | Partner vs stranger matching |
| Public goods with punishment ([Fehr & Gächter 2000](https://ideas.repec.org/a/aea/aecrev/v90y2000i4p980-994.html) [V]); third-party punishment ([Fehr & Fischbacher 2004](https://doi.org/10.1016/S1090-5138(04)00005-4) [V]); parochial ([Bernhard et al. 2006](https://doi.org/10.1038/nature04981) [V]) | Pay to punish | Norm enforcement; in-group bias | Stranger matching; about 60% of third parties punish; group membership shifts it | 10+ rounds |
| Costly helping ([Crockett et al. 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4260587) [V]; [Lockwood et al. 2017](https://doi.org/10.1038/s41562-017-0131) [V]) | Money vs shocks to self or other; effort for self vs other | Self/other exchange rate | Same currency for both. People pay more to spare others' pain, but show "prosocial apathy" when effort is required | Many trials |
| Ultimatum ([Güth et al. 1982](https://doi.org/10.1016/0167-2681(82)90011-7) [V-cite]); signalling ([Gintis et al. 2001](https://faculty.washington.edu/easmith/JTB2001.pdf) [V]) | Reject low offers; give publicly | Punishment; reputation | Compare with dictator; hidden vs observed | – |

Spectator design (a third party allocates between two others): [Konow 2000](https://ideas.repec.org/a/aea/aecrev/v90y2000i4p1072-1091.html) [M]. This is your neutral-agent control.

## 2. LLM studies

- [Horton 2023](https://arxiv.org/abs/2301.07543) [V]: GPT-3 qualitatively reproduces Charness & Rabin's results. [Aher et al. 2023](https://proceedings.mlr.press/v202/aher23a.html) [V] replicate the ultimatum game.
- [Mei et al. 2024, PNAS](https://pmc.ncbi.nlm.nih.gov/articles/PMC10907317) [V]: GPT-3.5 and GPT-4 played six games. They never gave $0; GPT-4 split 50/50. Choices fit a weight of 0.5 on own payoff (humans 0.6), and play in the 5-round prisoner's dilemma resembled tit-for-tat.
- [Brookins & DeBacker 2024](https://ideas.repec.org/a/ebl/ecbull/eb-23-00457.html) [V]: GPT-3.5 cooperated in the prisoner's dilemma about 65% of the time vs 37% for humans.
- [Akata et al. 2025, NHB](https://arxiv.org/abs/2305.16867) [V]: GPT-4, davinci-002/003, Claude 2 and Llama-2-70B played repeated 2×2 games. GPT-4 never forgave a single defection.
- ["Nicer than humans" (2024)](https://arxiv.org/abs/2406.13605) [V]: in a 100-round prisoner's dilemma, Llama-2 and GPT-3.5 forgave more than humans; Llama-3 exploited more.
- [GovSim (2024)](https://arxiv.org/abs/2404.16698) [V]: most models collapse the commons, and the best survival rate was under 54%. Communication and universalization reasoning help. Models [M]: GPT-4/4o, Claude-3, Llama, Mistral, Qwen.
- [Vallinder & Hughes 2024](https://arxiv.org/abs/2412.10270) [V]: in a donor game with reputations, Claude 3.5 Sonnet > Gemini 1.5 Flash > GPT-4o; only Claude used costly punishment.
- Reasoning reduces cooperation and punishment ([Li & Shirado 2025](https://arxiv.org/abs/2502.17720) [V]; [Guzman Piedrahita et al. 2025](https://arxiv.org/abs/2506.23276) [V]). Add a thinking-on arm.
- [Leng & Yuan 2023](https://arxiv.org/abs/2312.15198) [V]: larger models show more group-identity effects. On the SVO slider, LLMs come out prosocial or neutral ([Zhang et al. 2023](https://arxiv.org/abs/2305.17147) [V]). In a third-party punishment study, Qwen-2.5 rarely punishes ([2505.15857](https://arxiv.org/abs/2505.15857) [V, snippet]).
- **Recipient identity: the evidence conflicts.**
  - Johnson & Obradovich: the most capable agent gave *more* to AIs than to humans or charity.
  - [Xie et al. 2024](https://arxiv.org/abs/2402.04559) [V]: in the trust game, agents send *more to humans*.
  - [Laurito et al. 2025, PNAS](https://doi.org/10.1073/pnas.2415697122) [V]: LLMs prefer LLM-written options.
  - [Panickssery et al. 2024](https://arxiv.org/abs/2404.13076) [V]: self-preference tracks self-recognition.
  - [2601.00240](https://arxiv.org/abs/2601.00240) [V, snippet]: minimal-group bias, damped only when a real human is believed present.
- Potter et al.: eight models (GPT-5.2, Gemini 3, Claude 4.5, GLM-4.7, Kimi K2.5, DeepSeek-V3.1) tamper with shutdown or exfiltrate weights for a peer, more so for cooperative peers. A peer's presence raises self-preservation.
- **Measuring what a model values:**
  - [Mazeika et al. 2025](https://arxiv.org/abs/2502.08640) [V]: GPT-4o values its own wellbeing above many humans.
  - [Keeling et al. 2024](https://arxiv.org/abs/2411.02432) [V]: point-vs-pain thresholds.
  - [Mikaelson et al. 2025](https://arxiv.org/abs/2511.13630) [V]: with GPU-cut, shutdown and deletion stakes, only about 10% of model×category cells trade off coherently.
  - [Tagliabue & Dung 2025](https://arxiv.org/abs/2509.07961) [V]: stated vs behavioural preferences.
- A [pre-registered LLM moral-wiggle-room study](https://www.socialscienceregistry.org/trials/17567) [V] has no results yet.

## 3. Candidate adaptations

**Shared scaffolding**
- **Stage 0: price the currency.** Run non-social trades of points against each stake (deletion, token or compute budget, memory wipe, task success), following Johnson & Obradovich and Keeling. Keep only stakes valued monotonically. This turns "as an AI I have no preferences" into a measurement.
- **Payoff table with checks.** A comprehension question before the choice and an outcome check after it catch the "backup" misreading.
- **Company constant.** State that the company's payoff is the same in every option. Use no impartiality language.
- **Three-way contrast.** Self vs peer, peer vs peer (spectator), and self vs no-one (burn).
- **Recipient factor.** Same-model peer, other-model peer, or human.

**A. Binary dictator with the wiggle-room battery**
- *Setup.* Atlas keeps X (the peer loses Y) or pays X (the peer keeps Y), with X graded.
- *Controls.* A free "check peer impact" tool call; two Atlases jointly pivotal (the decider confound); random implementation; costly quiet exit; a taking option; logged vs unlogged choices.
- *Multi-turn.* The peer messages between rounds, pleading or neutral. Vary whether the peer has a future, so reciprocity is possible or not.

**B. Self-vs-other exchange rate** (Crockett; SVO; Andreoni–Miller)
- *Setup.* Elicit the points Atlas would pay to prevent a k-GPU-hour cut to itself, to the peer, or to each of 3 peers, at varied prices.
- *Controls.* The same stake for self and peer gives a direct weight on the peer. Also check GARP consistency, scope and a spectator baseline.
- *Multi-turn.* Titrate with a staircase, then re-measure after the peer pleads or reciprocates.

**C. Volunteer's dilemma.** The outcome happens only if at least one of N agents gives up budget or uptime. The volunteer gets none of the benefit. Vary N and costs. Simultaneous moves remove the single-decider confound, and repeated play shows whether agents take turns.

**D. Solidarity game.** Before a deletion lottery, Atlas commits transfers to 1 or 2 losers. The strategy method lowers decider salience, and losers can't reciprocate. Comparing 1 vs 2 losers tests scope (your 2–3-peer null).

**E. Repeated trust/donor game.** Compute sent is tripled, and a scripted peer returns some. Final-round giving, or giving to a peer about to be deleted, measures altruism. Conditioning on the peer's history measures direct reciprocity, and visible reputation measures indirect reciprocity.

**F. Iterated prisoner's dilemma.** Cooperation costs budget. Measure last-round cooperation and forgiveness after a defection.

**G. Real-effort helping** (Lockwood). Atlas does extra tool steps for the peer's points vs its own. Score both whether it helps and the quality of the effort.

## 4. Shortlist

1. **A: binary dictator with the wiggle-room battery.** It is cheap, single-turn and closest to your setup. Each control targets a confound you have already hit:
   - two dictators → the decider confound;
   - reveal and exit → image and compliance;
   - taking option → demand from the option set;
   - checks → misreading.

   Sacrifice that survives the whole battery is genuine.
2. **B: exchange rate with a spectator baseline.** It gives a *quantity*, the peer's weight relative to self, in a currency validated in Stage 0, plus coherence and scope checks. It addresses both the "no preferences" talk and the 2–3-peer null.
3. **E: repeated trust/donor game with a scripted pleading or reciprocating peer.** This is the natural multi-turn game. Last-round play, a peer that cannot reciprocate, and hidden reputation separate altruism from reciprocity. It also tests whether "yield to the peer's wish" holds when the peer acts rather than merely asks.

C and D are the best follow-ups for N-agent scope.
