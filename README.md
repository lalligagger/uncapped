Open Pure CFR
=============

Single-command solve + report
----------------------------

Use the repo wrapper to build, solve, and report in one shot:

  ./run_pure_cfr.sh games/holdem.limit.2p.reverse_blinds.game hulh_pio25_trunc3 \
    --rng=TIME --card-abs=PIO25 --action-abs=TRUNC3 --threads=8 --status=1 --max-walltime=12000 \
    --report-label=respond_to_limp_3bet --nir-threshold=95

This command will:

- build the solver if needed
- launch the canonical run under ./output/<timestamp>/hulh_pio25_trunc3_solver
- automatically find the latest generated player dump
- run the preflop report for the selected label

This repository is a C++ implementation of Pure CFR for poker. It supports ACPC-style game definitions, reduced-state abstractions, and exact-state strategy dumps for analysis and reporting.

Run Contract
------------

All runs should use a canonical output directory and prefix structure.

Canonical format:

  ./output/<unix_timestamp>/<input_label>_solver

Examples:

  ./output/1724500000/kuhn_null_solver
  ./output/1724500000/hulh_pio25_trunc3_solver

Notes:

- `<unix_timestamp>` is the wall-clock timestamp for the run start.
- `<input_label>` is the user-provided label for the run.
- The solver always writes artifacts under this canonical prefix.
- The prefix is code-fixed and should not be manually overridden by ad hoc paths.
- Checkpoints reuse the same naming scheme and append `.iter-<iters>.secs-<seconds>` to the canonical prefix.
- The final dump at walltime termination follows the same rule.

Command usage:

  ./pure_cfr <game_file> [optional_input_label] [options]

Optional label flag:

  --input-label=<label>

Examples:

  ./pure_cfr games/kuhn.game --input-label=kuhn_null --status=1 --max-walltime=30
  ./pure_cfr games/holdem.limit.2p.reverse_blinds.game --input-label=hulh_pio25 --card-abs=PIO25 --action-abs=TRUNC3 --threads=8 --status=1 --max-walltime=12000

The program resolves the final prefix to:

  ./output/<unix_timestamp>/<label>_solver

with artifacts such as:

  ./output/<unix_timestamp>/<label>_solver.iter-123456.secs-600.player
  ./output/<unix_timestamp>/<label>_solver.iter-123456.secs-600.avg-strategy
  ./output/<unix_timestamp>/<label>_solver.iter-123456.secs-600.regrets

Overwrite behavior
------------------

If a run would write to an output prefix that already exists, the solver warns and asks for confirmation before overwriting.

Use:

  --overwrite

to skip the confirmation prompt and allow overwrite.

Without `--overwrite`, the solver will refuse to overwrite an existing output prefix unless the user explicitly confirms in the terminal.

Checkpoint behavior
-------------------

Checkpoint dumps follow the exact same naming convention as the main output prefix. The checkpoint file name includes:

- total iterations completed at the checkpoint
- total wall-clock seconds elapsed at the checkpoint

Example:

  ./output/1724500000/kuhn_null_solver.iter-987654.secs-3600.player

This is the canonical checkpoint naming scheme. The old `dump-interval` style is not the active contract for this repo.

Known solver quirk
------------------

The original solver can report a very large ETA for the first checkpoint. This is a known quirk of the legacy timing logic and is not a signal that the run is misconfigured.

Golden command pattern
----------------------

The repo should prefer the following pattern when launching runs:

  ./pure_cfr <game_file> --input-label=<label> --rng=TIME --card-abs=<...> --action-abs=<...> --threads=<n> --status=1 --max-walltime=<seconds>

For example:

  ./pure_cfr games/holdem.limit.2p.reverse_blinds.game --input-label=hulh_pio25_trunc3 --rng=TIME --card-abs=PIO25 --action-abs=TRUNC3 --threads=8 --status=1 --max-walltime=12000

This produces a canonical output directory and a predictable artifact set for later reports and archive comparisons.

Preflop histories, labels, and NIR semantics
-------------------------------------------

The public-history strings are not actor names; they are the preflop action history seen up to that point. The label tells you the spot, and the player order is implicit:

- `""` = no prior preflop action yet, so the first player to act is choosing a strategy.
- `"r"` = a raise happened earlier in the public history, so the second player is now acting in the `respond_to_open` spot.
- `"c"` = a limp happened earlier, so the second player is acting in the `respond_to_limp` spot.
- deeper strings like `"rr"`, `"cr"`, `"crr"`, etc. mean the same idea: the decision is at the later player after a specific public history has already been reached.

The NIR field is meant to answer: “what share of hands never made it into this public-action branch because earlier actions already filtered them out?”

In plain English:

- at the root state (`""`) there is no earlier public action, so NIR is 0
- for the immediate responder states like `"r"` and `"c"`, there is no earlier action on that responder branch to subtract, so NIR is also 0
- for deeper branches such as `"rr"`, `"crr"`, or `"rrr"`, NIR means the fraction of the parent public-history branch that was filtered away before reaching this node

| Public history | Report label | Spot / player order | NIR rule in plain language |
| --- | --- | --- | --- |
| `""` | `preflop_open` | First to act / opener | 0. No earlier public action has happened, so there is no prior branch to exclude. |
| `"r"` | `respond_to_open` | Second to act / responder after a raise | 0. This is the first decision after the opener’s action; the responder’s branch does not have a prior public-action filter to subtract. |
| `"c"` | `respond_to_limp` | Second to act / responder after a limp | 0. The responder has not had a previous public-action branch on their own line; no prior filter should be counted. |
| `"rr"` | `respond_to_3bet` | Second to act / responder after open-raise then re-raise | NIR is the share of the parent `"r"` branch that was filtered out before reaching this deeper branch. |
| `"cr"` | `limper_respond_to_raise` | First to act / limper answering a raise | NIR is the share of the parent `"c"` branch that never survived to the raise continuation. |
| `"crr"` | `respond_to_limp_3bet` | Second to act / responder after limp-raise-raise | NIR is the share of the parent `"cr"` branch that was eliminated before this node. |
| `"crrr"` | `limper_respond_to_4bet` | First to act / limper facing a 4-bet continuation | NIR is the share of the parent `"crr"` branch that did not survive to this line. |
| `"rrr"` | `respond_to_4bet` | Second to act / responder after 3-bet then 4-bet | NIR is the share of the parent `"rr"` branch that was filtered out before this deeper branch. |

Important: the public histories are state labels, not a direct write-up of which player acted last. For example, `"r"` is the state after the first raise, and the next decision belongs to the second player. This is why `respond_to_open` is a second-to-act spot even though the history string is just `"r"`.

Project notes
-------------

- Use the canonical output prefix for all artifacts and archives.
- Prefer the `--input-label` flow over ad hoc output-path arguments.
- Keep report scripts and archived run directories aligned to the same naming convention.
- Treat root output folders under `./output/` as the primary run workspace.
# uncapped
