#!/bin/bash
# Fetch a single recipe page from the Wayback Machine, validating completeness.
# Usage: fetch_one.sh <fname> <timestamp> <original_url>
# Writes contribution/<fname> on success; prints "<fname>\t<status>\t<size>\t<snapshot>".
# Same logic as fetch.sh's inner loop, factored out so xargs can run it in parallel.
set -u
DEST="contribution"
fname="$1"; ts="$2"; orig="$3"

is_complete() {
  local f="$1" sz
  [ -f "$f" ] || return 1
  sz=$(wc -c < "$f" 2>/dev/null || echo 0)
  [ "$sz" -ge 3500 ] && return 0
  grep -aqiE 'method' "$f" 2>/dev/null && return 0
  return 1
}

# Download $1 -> $2, retrying once on failure (transient under concurrency).
dl() {
  curl -sL "$1" -o "$2" --max-time 60 2>/dev/null && [ -f "$2" ] && return 0
  sleep 2
  curl -sL "$1" -o "$2" --max-time 60 2>/dev/null
}

# Already present and complete? nothing to do.
if [ -f "$DEST/$fname" ] && is_complete "$DEST/$fname"; then
  echo -e "$fname\tskip\t$(wc -c < "$DEST/$fname")\t-"; exit 0
fi

tmp="$DEST/$fname.$$.new"; status=""; snap=""
# Attempt 1: newest snapshot from the worklist.
dl "https://web.archive.org/web/${ts}id_/${orig}" "$tmp"
if is_complete "$tmp"; then
  mv "$tmp" "$DEST/$fname"; status="ok"; snap="$ts"
else
  # Attempt 2: nearest capture to mid-2004 (pre-truncation era). A date-only
  # Wayback URL redirects to the closest snapshot, so no availability-API call.
  dl "https://web.archive.org/web/20040601id_/${orig}" "$tmp"
  if is_complete "$tmp"; then
    mv "$tmp" "$DEST/$fname"; status="ok-fallback"; snap="~2004"
  elif [ -s "$tmp" ]; then
    # Got a page but it was incomplete -> no complete capture exists. Record so
    # future passes skip it.
    rm -f "$tmp"; status="unrecoverable"; snap="-"
    echo "$fname" >> "$DEST/../harvest/unrecoverable.txt"
  else
    # No content at all -> transient; leave it to be retried next pass.
    rm -f "$tmp"; status="error"; snap="-"
  fi
fi
sz=$([ -f "$DEST/$fname" ] && wc -c < "$DEST/$fname" || echo 0)
echo -e "$fname\t$status\t$sz\t$snap"
