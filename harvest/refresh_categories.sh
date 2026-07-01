#!/bin/bash
# Fetch, for each category index page, the newest archived snapshot that actually
# lists recipes, and write it into contribution/. These pages define which recipes
# belong to which category.
#
# Robust against a flaky/rate-limited CDX API and the sify-era redesign:
#   - retries the timestamp lookup with backoff
#   - validates each timestamp is exactly 14 digits (rejects HTML error pages)
#   - walks snapshots newest-first, accepting the first page that contains recipe
#     links (contribNNN.html); many late snapshots are linkless redirect pages
#   - downloads to a temp file and only overwrites the good copy on success
set -u
cd "$(dirname "$0")/.."
DEST="contribution"
# Categories to refresh: all by default, or just those named on the command line.
CATS="${*:-vegetables paneer soya daal curries rice roti dosas bread regional east \
snacks pakora chutney raita salad soup refreshment sweets cakes mushroom assorted \
microwave south chicken redmeat seafood egg nonvegsweets index}"

# The sify-era redesign (~2006+) left some snapshots as linkless redirect/error
# pages. So we don't blindly take the newest capture: we list all 200-snapshot
# timestamps (newest first) and accept the first one whose page actually contains
# recipe links. MAX_TRIES caps how far back we walk per category.
MAX_TRIES=25

# Order to walk snapshots: "desc" (newest first, default) maximises recipe count;
# "asc" (oldest first) rescues categories whose link-bearing captures predate the
# sify-era redesign, since post-2006 snapshots can be linkless redirect pages.
ORDER="${ORDER:-desc}"

# Echo all valid (14-digit) 200-snapshot timestamps in $ORDER, or nothing.
list_ts() {
  local page="$1" out sortflag="-rn"
  [ "$ORDER" = "asc" ] && sortflag="-n"
  for attempt in 1 2 3; do
    out=$(curl -s "http://web.archive.org/cdx/search/cdx?url=bawarchi.com/contribution/${page}&output=text&fl=timestamp&filter=statuscode:200&limit=-1" \
          --max-time 60 2>/dev/null | grep -E '^[0-9]{14}$' | sort $sortflag | uniq)
    if [ -n "$out" ]; then echo "$out"; return 0; fi
    sleep $((attempt * 4))
  done
  return 1
}

for c in $CATS; do
  tss=$(list_ts "${c}.html") || { echo "$c: no snapshot list from CDX (keeping existing)"; continue; }
  tmp="$DEST/${c}.html.new"; ok=0; tries=0
  for ts in $tss; do
    tries=$((tries+1)); [ "$tries" -gt "$MAX_TRIES" ] && break
    url="https://web.archive.org/web/${ts}id_/http://www.bawarchi.com/contribution/${c}.html"
    code=$(curl -sL "$url" -o "$tmp" -w "%{http_code}" --max-time 45 2>/dev/null || echo 000)
    sz=$(wc -c < "$tmp" 2>/dev/null || echo 0)
    # A real category index links to recipe pages; a redirect/error page does not.
    # -a forces text mode: several archived pages are ISO-8859 and grep otherwise
    # treats them as binary and reports no match.
    if [ "$code" = "200" ] && [ "$sz" -gt 200 ] && grep -aqiE 'contrib[0-9]+\.html' "$tmp"; then
      mv "$tmp" "$DEST/${c}.html"
      links=$(grep -aoiE 'contrib[0-9]+\.html' "$DEST/${c}.html" | sort -u | wc -l | tr -d ' ')
      echo "$c: OK ${sz}B ${links} links (snapshot $ts, try $tries)"
      ok=1; break
    fi
    rm -f "$tmp"; sleep 1
  done
  [ "$ok" -eq 0 ] && echo "$c: FAILED — no snapshot with recipe links in newest $MAX_TRIES (keeping existing)"
  sleep 1
done
