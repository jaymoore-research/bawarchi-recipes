#!/bin/bash
# Download recipe pages listed in harvest/worklist.tsv from the Wayback Machine.
#
# The worklist records each recipe's NEWEST 200 snapshot, but many late
# (sify-era, ~2006+) captures are truncated stubs that cut off in the page
# navigation before any recipe content. So we don't trust size>200 alone:
#   - a download is "complete" only if it looks like a real recipe
#     (contains a "method" marker, or is comfortably larger than a nav-only stub)
#   - if the newest snapshot is truncated, we fall back to the closest snapshot
#     to mid-2004 (the pre-truncation era) via the lightweight availability API
#   - recipes with no complete capture anywhere are logged as unrecoverable,
#     never kept as stubs
#
# Resumable: skips recipes already present AND complete. Rate-limited.
set -u
cd "$(dirname "$0")/.."               # project root
WORKLIST="${WORKLIST:-harvest/worklist.tsv}"
DEST="contribution"
MANIFEST="${MANIFEST:-harvest/fetch-manifest.tsv}"
UNREC="${UNREC:-harvest/unrecovered.txt}"

echo -e "file\tstatus\tsize\tsnapshot" > "$MANIFEST"
: > "$UNREC"

# A complete recipe page carries recipe content; a truncated stub is nav only.
is_complete() {
  local f="$1" sz
  sz=$(wc -c < "$f" 2>/dev/null || echo 0)
  [ "$sz" -ge 3500 ] && return 0
  grep -aqiE 'method' "$f" 2>/dev/null && return 0
  return 1
}

# Fetch $1 -> $2 (raw archived HTML via the id_ suffix).
dl() { curl -sL "$1" -o "$2" --max-time 60 2>/dev/null; }

total=$(($(wc -l < "$WORKLIST") - 1)); i=0; got=0; via_fallback=0; skip=0; unrec=0
while IFS=$'\t' read -r fname ts orig; do
  [ "$fname" = "file" ] && continue
  i=$((i+1))

  # Resume: keep recipes we already have complete (protects the 2001 corpus).
  if [ -f "$DEST/$fname" ] && is_complete "$DEST/$fname"; then
    skip=$((skip+1)); continue
  fi

  tmp="$DEST/$fname.new"; status=""; snap=""

  # Attempt 1: the newest snapshot from the worklist.
  dl "https://web.archive.org/web/${ts}id_/${orig}" "$tmp"
  if is_complete "$tmp"; then
    mv "$tmp" "$DEST/$fname"; got=$((got+1)); status="ok"; snap="$ts"
  else
    # Attempt 2: closest snapshot to mid-2004 (pre-truncation era).
    alt=$(curl -s "http://archive.org/wayback/available?url=${orig}&timestamp=20040601" \
          --max-time 30 2>/dev/null | grep -oE '"timestamp"[: ]*"[0-9]{14}"' | grep -oE '[0-9]{14}' | head -1)
    if [ -n "$alt" ] && [ "$alt" != "$ts" ]; then
      dl "https://web.archive.org/web/${alt}id_/${orig}" "$tmp"
      if is_complete "$tmp"; then
        mv "$tmp" "$DEST/$fname"; got=$((got+1)); via_fallback=$((via_fallback+1))
        status="ok-fallback"; snap="$alt"
      fi
    fi
    if [ "$status" = "" ]; then
      rm -f "$tmp"; unrec=$((unrec+1)); status="unrecoverable"; snap="-"
      echo "$fname" >> "$UNREC"
    fi
  fi

  sz=$([ -f "$DEST/$fname" ] && wc -c < "$DEST/$fname" || echo 0)
  echo -e "$fname\t$status\t$sz\t$snap" >> "$MANIFEST"
  [ $((i % 100)) -eq 0 ] && echo "[$i/$total] got=$got (fallback=$via_fallback) skip=$skip unrec=$unrec last=$fname"
  sleep 0.7
done < "$WORKLIST"
echo "DONE: total=$total got=$got (via fallback=$via_fallback) skip=$skip unrecoverable=$unrec"
echo "unrecoverable list: $UNREC"
