#!/usr/bin/env bash
#
# build-whitepaper.sh — Generate Bitcoin Stamps whitepaper PDF, HTML, and combined Markdown
#
# Usage:
#   ./build-whitepaper.sh                    # Build all formats
#   ./build-whitepaper.sh --pdf-only         # PDF only
#   ./build-whitepaper.sh --deploy           # Build + copy to bitcoinstamps.xyz/docs/public/
#   ./build-whitepaper.sh --version "1.1"    # Override version number
#
# Requirements: pandoc, typst (https://typst.app)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Configuration ---
VERSION="${VERSION:-1.0}"
BUILD_DATE="$(date +%Y-%m-%d)"
DEPLOY_TARGET="${DEPLOY_TARGET:-$(cd "$SCRIPT_DIR/../../../bitcoinstamps.xyz/docs/public" 2>/dev/null && pwd)}"
# Fallback: look for it from workspace root
if [ -z "$DEPLOY_TARGET" ] || [ ! -d "$DEPLOY_TARGET" ]; then
    WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    DEPLOY_TARGET="$WORKSPACE_ROOT/bitcoinstamps.xyz/docs/public"
fi

# Protocol genesis dates (from indexer config.py)
GENESIS_DATE="March 29, 2023"        # Block 779,652 — First Bitcoin Stamp
SRC20_DATE="April 20, 2023"          # Block 788,041 — First SRC-20 (KEVIN)
NATIVE_DATE="April 20, 2023"         # Block 793,068 — Native encoding
OLGA_DATE="October 15, 2023"         # Block 865,000 — OLGA activation

# Section files in order
SECTIONS=(
    introduction.md
    architecture.md
    token-standards.md
    economics.md
    improvement-proposals.md
    implementation.md
    security.md
    future.md
)

OUTPUT_DIR="$SCRIPT_DIR/build"
COMBINED_MD="$OUTPUT_DIR/bitcoin-stamps-whitepaper-combined.md"
OUTPUT_PDF="$OUTPUT_DIR/bitcoin-stamps-whitepaper.pdf"
OUTPUT_HTML="$OUTPUT_DIR/bitcoin-stamps-whitepaper.html"

# --- Parse arguments ---
PDF_ONLY=false
DEPLOY=false

for arg in "$@"; do
    case "$arg" in
        --pdf-only)   PDF_ONLY=true ;;
        --deploy)     DEPLOY=true ;;
        --version=*)  VERSION="${arg#--version=}" ;;
        --version)    shift; VERSION="${2:-$VERSION}" ;;
        --help|-h)
            echo "Usage: $0 [--pdf-only] [--deploy] [--version X.Y]"
            echo ""
            echo "  --pdf-only    Generate PDF only (skip HTML and combined markdown)"
            echo "  --deploy      Copy outputs to bitcoinstamps.xyz/docs/public/"
            echo "  --version X.Y Override version number (default: $VERSION)"
            exit 0
            ;;
    esac
done

# --- Dependency checks ---
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "ERROR: $1 is required but not found."
        echo "  Install: $2"
        exit 1
    fi
}

check_dep pandoc "apt install pandoc"
check_dep typst "curl -sSL https://github.com/typst/typst/releases/latest | install to ~/.local/bin/"

echo "=== Bitcoin Stamps Whitepaper Build ==="
echo "  Version:  $VERSION"
echo "  Date:     $BUILD_DATE"
echo "  Pandoc:   $(pandoc --version | head -1)"
echo "  Typst:    $(typst --version)"
echo ""

mkdir -p "$OUTPUT_DIR"

# --- Step 1: Combine markdown files ---
echo "[1/4] Combining markdown sections..."

clean_section() {
    # Remove YAML frontmatter, inter-file navigation, fix relative links,
    # and ensure blank lines before list items (required for proper Pandoc parsing)
    awk '
        BEGIN { in_fm=0; seen_fm=0; prev="" }
        /^---$/ && !seen_fm { in_fm=1; seen_fm=1; next }
        /^---$/ && in_fm    { in_fm=0; next }
        in_fm { next }
        /^\*\*Next\*\*:/ { next }
        /^\*\*Previous\*\*:/ { next }
        # Insert blank line before list item if previous line was non-empty text
        /^- / && prev != "" && prev !~ /^- / && prev !~ /^[[:space:]]*$/ && prev !~ /^#/ {
            print ""
        }
        { print; prev = $0 }
    ' "$1"
}

{
    # Title page metadata
    cat <<FRONTMATTER
---
title: "Bitcoin Stamps Protocol"
subtitle: "A Technical Whitepaper — Version $VERSION"
author:
  - The Original Trinity (Mikeinspace, Arwyn, Reinamora)
  - Bitcoin Stamps Community
date: "$BUILD_DATE"
version: "$VERSION"
lang: en
mainfont: "Liberation Serif"
sansfont: "Liberation Sans"
monofont: "Liberation Mono"
fontsize: 10pt
papersize: a4
margin-left: 1in
margin-right: 1in
margin-top: 1in
margin-bottom: 1in
abstract: |
  Bitcoin Stamps is a metaprotocol for creating permanent, immutable digital
  assets on Bitcoin through direct UTXO storage. Unlike witness-data approaches,
  Bitcoin Stamps embed asset data in transaction outputs using bare multisig and
  P2WSH encoding, ensuring universal node storage and consensus-critical permanence.

  The protocol evolved from Counterparty foundations (block 779,652, $GENESIS_DATE)
  through native Bitcoin encoding (block 793,068) to P2WSH optimization via OLGA
  (block 865,000, $OLGA_DATE). Built on account-based asset tracking, Bitcoin Stamps
  support fungible tokens (SRC-20), non-fungible assets (base stamps), decentralized
  naming (SRC-101), and composable recursion (SRC-721).
---

FRONTMATTER

    # Version history table
    cat <<'VHISTORY'
# Version History

| Version | Date | Description |
|:-------:|------|-------------|
VHISTORY

    echo "| $VERSION | $BUILD_DATE | Current release — factual corrections, OLGA clarifications, condensed future roadmap |"
    cat <<'VHISTORY'
| 0.9 | 2026-02-16 | Initial whitepaper draft — full protocol specification |
| — | March 29, 2023 | Protocol genesis — first Bitcoin Stamp at block 779,652 |

---

VHISTORY

    # Table of contents placeholder (Typst/Pandoc generates real one)
    # Combine sections with page breaks
    for i in "${!SECTIONS[@]}"; do
        section="${SECTIONS[$i]}"
        section_num=$((i + 1))

        if [ ! -f "$section" ]; then
            echo "WARNING: Section file not found: $section" >&2
            continue
        fi

        # Page break before each section (raw Typst block via Pandoc)
        if [ "$i" -gt 0 ]; then
            echo ""
            echo '```{=typst}'
            echo '#pagebreak()'
            echo '```'
            echo ""
        fi

        # Clean section: strip frontmatter, navigation links, relative refs
        clean_section "$section"
        echo ""
    done

} > "$COMBINED_MD"

LINES=$(wc -l < "$COMBINED_MD")
echo "  Combined: $LINES lines → $COMBINED_MD"

# --- Step 2: Generate PDF via Pandoc + Typst ---
echo "[2/4] Generating PDF..."

pandoc "$COMBINED_MD" \
    -o "$OUTPUT_PDF" \
    --pdf-engine=typst \
    --toc \
    --toc-depth=3 \
    --number-sections \
    -f markdown-citations \
    2>&1

PDF_SIZE=$(du -h "$OUTPUT_PDF" | cut -f1)
echo "  PDF: $PDF_SIZE → $OUTPUT_PDF"

if [ "$PDF_ONLY" = true ]; then
    echo ""
    echo "=== Done (PDF only) ==="
    echo "  $OUTPUT_PDF ($PDF_SIZE)"
    exit 0
fi

# --- Step 3: Generate standalone HTML ---
echo "[3/4] Generating HTML..."

pandoc "$COMBINED_MD" \
    -o "$OUTPUT_HTML" \
    --standalone \
    --toc \
    --toc-depth=3 \
    --number-sections \
    --metadata title="Bitcoin Stamps Protocol: A Technical Whitepaper" \
    --metadata date="$BUILD_DATE" \
    -f markdown-citations \
    2>&1

# Inject minimal CSS for clean HTML rendering
TEMP_HTML=$(mktemp)
sed '/<\/head>/i\
<style>\
body { max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.7; color: #1a1a1a; }\
h1 { font-size: 2rem; border-bottom: 2px solid #e2e2e2; padding-bottom: 0.5rem; }\
h2 { font-size: 1.5rem; margin-top: 2.5rem; border-bottom: 1px solid #eee; padding-bottom: 0.3rem; }\
h3 { font-size: 1.2rem; margin-top: 2rem; }\
code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }\
pre { background: #f4f4f4; padding: 1rem; border-radius: 6px; overflow-x: auto; }\
pre code { background: none; padding: 0; }\
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }\
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }\
th { background: #f8f8f8; font-weight: 600; }\
tr:nth-child(even) { background: #fafafa; }\
blockquote { border-left: 4px solid #ddd; margin: 1rem 0; padding: 0.5rem 1rem; color: #555; }\
a { color: #2563eb; text-decoration: none; }\
a:hover { text-decoration: underline; }\
nav#TOC { background: #f8f9fa; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; }\
nav#TOC > ul { margin: 0; }\
@media print { body { max-width: none; } nav#TOC { break-after: page; } h1, h2 { break-after: avoid; } }\
</style>' "$OUTPUT_HTML" > "$TEMP_HTML"
mv "$TEMP_HTML" "$OUTPUT_HTML"

HTML_SIZE=$(du -h "$OUTPUT_HTML" | cut -f1)
echo "  HTML: $HTML_SIZE → $OUTPUT_HTML"

# --- Step 4: Finalize combined markdown ---
echo "[4/4] Finalizing combined markdown..."
MD_SIZE=$(du -h "$COMBINED_MD" | cut -f1)
echo "  Markdown: $MD_SIZE → $COMBINED_MD"

# --- Deploy ---
if [ "$DEPLOY" = true ]; then
    echo ""
    echo "[deploy] Copying to bitcoinstamps.xyz..."

    if [ ! -d "$DEPLOY_TARGET" ]; then
        echo "  ERROR: Deploy target not found: $DEPLOY_TARGET"
        echo "  Expected: bitcoinstamps.xyz/docs/public/"
        exit 1
    fi

    cp "$OUTPUT_PDF"  "$DEPLOY_TARGET/bitcoin-stamps-whitepaper.pdf"
    cp "$OUTPUT_HTML"  "$DEPLOY_TARGET/bitcoin-stamps-whitepaper.html"
    cp "$COMBINED_MD"  "$DEPLOY_TARGET/bitcoin-stamps-whitepaper-combined.md"

    echo "  Deployed 3 files to $DEPLOY_TARGET/"
fi

# --- Summary ---
echo ""
echo "=== Build Complete ==="
echo "  Version:  $VERSION ($BUILD_DATE)"
echo "  PDF:      $OUTPUT_PDF ($PDF_SIZE)"
echo "  HTML:     $OUTPUT_HTML ($HTML_SIZE)"
echo "  Markdown: $COMBINED_MD ($MD_SIZE)"
echo ""
echo "To deploy:  $0 --deploy"
echo "To bump:    $0 --version 1.1 --deploy"
