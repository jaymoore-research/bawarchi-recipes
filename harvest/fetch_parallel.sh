#!/bin/bash
# Parallel driver over recipes still missing from contribution/.
# Runs harvest/fetch_one.sh with xargs -P for throughput (Wayback tolerates
# moderate concurrency on the content endpoint). Resumable: recomputes the
# missing set each run, so it can be re-run until nothing recoverable remains.
#
# Env: JOBS (default 6) concurrent workers.
set -u
cd "$(dirname "$0")/.."
WORKLIST="harvest/worklist.tsv"
MANIFEST="harvest/fetch-manifest.tsv"
JOBS="${JOBS:-6}"

# Recipes in the worklist, minus those on disk AND those already confirmed to
# have no complete capture anywhere (harvest/unrecoverable.txt), so repeated
# passes converge instead of re-burning time on truncated-only recipes.
UNREC="harvest/unrecoverable.txt"
touch "$UNREC"
comm -23 \
  <(tail -n +2 "$WORKLIST" | cut -f1 | sort) \
  <(cat <(ls contribution/ | grep -E '^contrib[0-9]+\.html$') "$UNREC" | sort -u) \
  > /tmp/bw_missing.$$

n=$(wc -l < /tmp/bw_missing.$$ | tr -d ' ')
echo "missing before: $n  (JOBS=$JOBS)"
[ "$n" -eq 0 ] && { rm -f /tmp/bw_missing.$$; echo "nothing to do"; exit 0; }

echo -e "file\tstatus\tsize\tsnapshot" > "$MANIFEST"

# Emit "fname<TAB>ts<TAB>orig" for each missing recipe, then fan out.
awk -F'\t' 'NR==FNR{m[$1]=1; next} ($1 in m)' /tmp/bw_missing.$$ <(tail -n +2 "$WORKLIST") \
  | xargs -P "$JOBS" -L1 bash harvest/fetch_one.sh \
  | tee -a "$MANIFEST" \
  | awk -F'\t' '{c[$2]++} END{for(k in c) printf "  %s: %d\n", k, c[k]}'

rm -f /tmp/bw_missing.$$
remaining=$(comm -23 \
  <(tail -n +2 "$WORKLIST" | cut -f1 | sort) \
  <(ls contribution/ | grep -E '^contrib[0-9]+\.html$' | sort) | wc -l | tr -d ' ')
echo "missing after: $remaining"
