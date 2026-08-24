# QUBO Formulation for Resilience Search

Energy of a binary configuration \(x \in \{0,1\}^n\):

\[
E(x) = \sum_i h_i x_i + \sum_{i<j} J_{ij} x_i x_j
\]

## Terms

| Term | Default | Role |
|------|---------|------|
| \(h_i\) = `select_penalty` | −1.0 | Negative → favor selecting atoms (coverage) |
| \(J_{ij}\) support = \(-\alpha \cdot c_{ij}\) | \(\alpha = 1.5\) | Positive consistency lowers energy when both selected |
| \(J_{ij}\) redundancy = \(+\rho \cdot r_{ij}\) | \(\rho = 2.0\) | Near-duplicates raise energy when both selected |

### Redundancy weight \(r_{ij}\)

1. **Lexical:** Jaccard similarity on tokens if \(\ge\) `redundancy_threshold` (default **0.22**)
2. **Paraphrase soft penalty:** if consistency \(c_{ij} \ge 0.85\), also contribute  
   \(0.45\,c_{ij} + 0.25\cdot\mathrm{sim}\)  
   so highly supporting near-paraphrases are discouraged even when wording differs

## Effect

- Mutually supporting, non-duplicate claims → still preferred together  
- Near-duplicate / paraphrase claims → co-selection penalized → compressed packets stay diverse  
- Conflicting claims (\(c_{ij} < 0\)) → still discouraged together  

## Solvers

Classical simulated annealing (stdlib) or greedy constructive search minimize \(E\).
Same QUBO can be handed to hybrid/quantum annealers offline.

## CLI

```bash
coherence search --greedy --max-size 6
coherence search --redundancy-scale 2 --redundancy-threshold 0.22
coherence search --redundancy-scale 0   # disable redundancy term
```
