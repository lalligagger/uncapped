#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run_pure_cfr.sh <game_file> <run_label> [solver args...] [--report-label=<label>] [--nir-threshold=<pct>]

Examples:
  ./run_pure_cfr.sh games/kuhn.game kuhn_null --rng=TIME --threads=1 --status=1 --max-walltime=30
  ./run_pure_cfr.sh games/holdem.limit.2p.reverse_blinds.game hulh_pio25_trunc3 \
    --rng=TIME --card-abs=PIO25 --action-abs=TRUNC3 --threads=8 --status=1 --max-walltime=12000 \
    --report-label=respond_to_limp_3bet --nir-threshold=95

This command:
  1) runs the canonical solver under ./output/<timestamp>/<label>_solver
  2) finds the newest generated player dump for that prefix
  3) runs the preflop report on that dump
EOF
}

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

game_file="$1"
run_label="$2"
shift 2

report_label="all"
nir_threshold="95"
solver_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --report-label=*)
      report_label="${1#*=}"
      ;;
    --report-label)
      shift
      report_label="${1:-all}"
      ;;
    --nir-threshold=*)
      nir_threshold="${1#*=}"
      ;;
    --nir-threshold)
      shift
      nir_threshold="${1:-95}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      solver_args+=("$1")
      ;;
  esac
  shift
done

if [[ ! -f "$game_file" ]]; then
  echo "Game file not found: $game_file" >&2
  exit 1
fi

if [[ ! -x ./pure_cfr ]]; then
  echo "Solver binary not found; building now..."
  make -j4
fi

./pure_cfr "$game_file" --input-label="$run_label" "${solver_args[@]}"

latest_player="$(find ./output -type f -path "./output/*/${run_label}_solver*.player" -print 2>/dev/null | sort | tail -n 1)"
if [[ -z "$latest_player" ]]; then
  echo "No player dump found for label [$run_label] under ./output/" >&2
  exit 1
fi

echo "Generating report for player: $latest_player"
python3 utils/preflop_frequency_report.py "$latest_player" --label "$report_label" --nir-threshold "$nir_threshold"
