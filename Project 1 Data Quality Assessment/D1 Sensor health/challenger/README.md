# D1 Challenger Detector

This directory is an isolated retrospective development track for the D1
Spike and Step detectors. It never writes to the released D1 scores, state
machine, release manifest, or D1-D5 aggregation inputs.

The challenger contains one causal multiscale GLR core:

- minute-level robust innovations for impulse spikes and short bursts;
- the frozen Section 1.1 routed hourly innovation for temporary and persistent
  level shifts;
- the released adjacent-window KS detector as the persistence comparator;
- event-level threshold calibration under a fixed false-alarm budget.

The current record supports retrospective development and a terminal shadow
evaluation only. External or future confirmation remains pending.

Frozen execution `D1C-20260802-v1.1` completed all 384 event designs. The
track-level alarm-rate gates passed, but none of the four mechanisms met the
prespecified paired recall-improvement rule. The challenger is therefore not
eligible to replace the released D1 detector. This negative result is retained
as an applicability boundary; no release threshold was relaxed.

Run from the project root:

```powershell
python "D1 Sensor health/challenger/run_challenger.py"
python -m pytest "D1 Sensor health/challenger/tests" -q
```
