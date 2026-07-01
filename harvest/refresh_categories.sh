#!/bin/bash
# Fetch the latest HTTP-200 snapshot of each category index page into contribution/.
# These pages define which recipes belong to which category.
set -u
cd "$(dirname "$0")/.."
DEST="contribution"
CATS="vegetables paneer soya daal curries rice roti dosas bread regional east \
snacks pakora chutney raita salad soup refreshment sweets cakes mushroom assorted \
microwave south chicken redmeat seafood egg nonvegsweets index"

for c in $CATS; do
  # newest 200 snapshot for this exact page
  ts=$(curl -s "http://web.archive.org/cdx/search/cdx?url=bawarchi.com/contribution/${c}.html&output=text&fl=timestamp&filter=statuscode:200&limit=-1" --max-time 60 2>/dev/null | tail -1)
  if [ -z "$ts" ]; then echo "no snapshot: $c"; continue; fi
  url="https://web.archive.org/web/${ts}id_/http://www.bawarchi.com/contribution/${c}.html"
  tmp="$DEST/${c}.html.new"
  code=$(curl -sL "$url" -o "$tmp" -w "%{http_code}" --max-time 45 2>/dev/null || echo 000)
  sz=$(wc -c < "$tmp" 2>/dev/null || echo 0)
  echo "$c: $code ${sz}B (snapshot $ts)"
  if [ "$code" = "200" ] && [ "$sz" -gt 200 ]; then
    mv "$tmp" "$DEST/${c}.html"       # only overwrite the good copy on success
  else
    echo "  FAILED, keeping existing $c.html"; rm -f "$tmp"
  fi
  sleep 0.8
done
