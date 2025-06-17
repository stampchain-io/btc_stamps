#!/usr/bin/env python3
"""
OpenStamp Database Token Mismatch Analyzer

This script analyzes the mismatch between tokens returned by the OpenStamp API
and tokens that exist in our SRC20Valid database table. This helps identify
why market data isn't being updated for all tokens despite the API returning
hundreds of records.

Usage:
    cd indexer && poetry run python tools/debug/analyze_openstamp_db_mismatch.py
"""

import os
import sys
from typing import Set, Dict
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from indexer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ Loaded environment variables from {env_path}", file=sys.stderr)
else:
    print(f"⚠️  Warning: .env file not found at {env_path}", file=sys.stderr)

from index_core.openstamp_client import get_openstamp_client
from index_core.database_manager import DatabaseManager


class OpenStampDBMismatchAnalyzer:
    """Analyzes token mismatches between OpenStamp API and local database."""

    def __init__(self):
        """Initialize the analyzer."""
        print(f"🔗 Connecting to database: {os.environ.get('RDS_DATABASE', 'btc_stamps')}", file=sys.stderr)
        print(f"🌐 Database host: {os.environ.get('RDS_HOSTNAME', 'localhost')}", file=sys.stderr)
        self.db_manager = DatabaseManager()
        self.openstamp_client = get_openstamp_client()

    def get_openstamp_tokens(self) -> Set[str]:
        """Fetch all tokens from OpenStamp API."""
        try:
            print("🌐 Fetching tokens from OpenStamp API...")
            api_response = self.openstamp_client.fetch_all_market_data()
            
            if not api_response:
                print("❌ No response from OpenStamp API")
                return set()
            
            all_tokens = set(api_response.get_all_tickers())
            print(f"✅ OpenStamp API returned {len(all_tokens)} total tokens")
            
            # Filter tokens <= 5 characters (SRC-20 spec)
            filtered_tokens = {token for token in all_tokens if len(token) <= 5}
            excluded_count = len(all_tokens) - len(filtered_tokens)
            
            print(f"🔧 Filtered to {len(filtered_tokens)} tokens (≤5 chars)")
            if excluded_count > 0:
                print(f"❌ Excluded {excluded_count} tokens (>5 chars)")
                excluded_tokens = sorted([token for token in all_tokens if len(token) > 5])
                print(f"   Excluded: {excluded_tokens[:10]}{'...' if len(excluded_tokens) > 10 else ''}")
            
            return filtered_tokens
            
        except Exception as e:
            print(f"❌ Error fetching OpenStamp tokens: {e}")
            return set()

    def get_database_tokens(self) -> Set[str]:
        """Fetch all SRC-20 tokens from local database."""
        try:
            print("🗄️  Fetching tokens from SRC20Valid database...")
            db = self.db_manager.connect()
            
            try:
                with db.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT tick 
                        FROM SRC20Valid 
                        WHERE tick IS NOT NULL 
                        AND tick != ''
                        ORDER BY tick
                    """)
                    
                    results = cursor.fetchall()
                    tokens = {row[0] for row in results}
                    print(f"✅ Database contains {len(tokens)} unique SRC-20 tokens")
                    return tokens
                    
            finally:
                db.close()
                
        except Exception as e:
            print(f"❌ Error fetching database tokens: {e}")
            return set()

    def run_analysis(self) -> Dict[str, any]:
        """Run the complete analysis."""
        print("🔍 Starting OpenStamp Database Token Mismatch Analysis")
        print("=" * 60)
        
        # Fetch token sets
        openstamp_tokens = self.get_openstamp_tokens()
        db_tokens = self.get_database_tokens()
        
        if not openstamp_tokens or not db_tokens:
            print("❌ Cannot continue analysis without both token sets")
            return {}
        
        print("\n📊 TOKEN SET COMPARISON")
        print("-" * 30)
        
        # Basic set operations
        exact_matches = openstamp_tokens & db_tokens
        openstamp_only = openstamp_tokens - db_tokens
        db_only = db_tokens - openstamp_tokens
        
        print(f"📈 OpenStamp tokens: {len(openstamp_tokens)}")
        print(f"🗄️  Database tokens: {len(db_tokens)}")
        print(f"✅ Exact matches: {len(exact_matches)}")
        print(f"🌐 OpenStamp only: {len(openstamp_only)}")
        print(f"🗄️  Database only: {len(db_only)}")
        
        if openstamp_only:
            print(f"\n🌐 Sample OpenStamp-only tokens: {sorted(list(openstamp_only))[:10]}")
            print("\n🚨 ALL OpenStamp-only tokens (first 50):")
            for i, token in enumerate(sorted(list(openstamp_only))[:50]):
                print(f"   {i + 1:2d}. {token}")
            if len(openstamp_only) > 50:
                print(f"   ... and {len(openstamp_only) - 50} more")
        
        if db_only:
            print(f"\n🗄️ Sample Database-only tokens: {sorted(list(db_only))[:10]}")
        
        # Case-insensitive analysis 
        print("\n🔍 CASE-INSENSITIVE ANALYSIS")
        print("-" * 40)
        
        # Create case-insensitive sets
        openstamp_lower = {token.lower() for token in openstamp_tokens}
        db_lower = {token.lower() for token in db_tokens}
        
        case_insensitive_matches = openstamp_lower & db_lower
        openstamp_only_case_insensitive = openstamp_lower - db_lower
        
        print(f"📊 Case-insensitive matches: {len(case_insensitive_matches)}")
        print(f"🌐 OpenStamp-only (case-insensitive): {len(openstamp_only_case_insensitive)}")
        
        if openstamp_only_case_insensitive:
            print("\n🚨 TOKENS TRULY MISSING FROM DATABASE:")
            print("   (These OpenStamp tokens don't exist in your database even case-insensitively)")
            
            # Debug emoji case conversion issues
            print("\n🔍 DEBUGGING EMOJI CASE CONVERSION:")
            for token in sorted(list(openstamp_only_case_insensitive)):
                if any(ord(c) > 127 for c in token):  # Contains non-ASCII (likely emoji)
                    token_upper = token.upper()
                    token_lower = token.lower()
                    
                    print(f"   OpenStamp: {repr(token)}")
                    print(f"   .upper():  {repr(token_upper)}")
                    print(f"   .lower():  {repr(token_lower)}")
                    
                    # Check if any database token matches when normalized differently
                    potential_matches = []
                    for db_token in db_tokens:
                        if any(ord(c) > 127 for c in db_token):  # Also has Unicode
                            # Try various case combinations
                            if (db_token.lower() == token_lower or 
                                db_token.upper() == token_upper or
                                db_token.lower() == token.lower() or
                                db_token.upper() == token.upper()):
                                potential_matches.append(db_token)
                    
                    if potential_matches:
                        print(f"   🎯 FOUND MATCH: {potential_matches}")
                    else:
                        print("   ❌ No database match found")
                    print()
            
            # Categorize missing tokens  
            emoji_tokens = []
            regular_tokens = []
            
            for token in sorted(list(openstamp_only_case_insensitive)):
                if any(ord(c) > 127 for c in token):  # Contains non-ASCII (likely emoji)
                    emoji_tokens.append(token)
                else:
                    regular_tokens.append(token)
            
            if regular_tokens:
                print(f"\n   📝 Regular missing tokens ({len(regular_tokens)}):")
                for i, token in enumerate(regular_tokens[:15]):
                    print(f"      {i + 1:2d}. {token}")
                if len(regular_tokens) > 15:
                    print(f"      ... and {len(regular_tokens) - 15} more")
            
            if emoji_tokens:
                print(f"\n   😀 Emoji/Unicode missing tokens ({len(emoji_tokens)}):")
                for i, token in enumerate(emoji_tokens[:10]):
                    print(f"      {i + 1:2d}. {token} (repr: {repr(token)})")
                if len(emoji_tokens) > 10:
                    print(f"      ... and {len(emoji_tokens) - 10} more")
        
        # Count missing token categories
        emoji_missing = 0
        regular_missing = 0
        if openstamp_only_case_insensitive:
            for token in openstamp_only_case_insensitive:
                if any(ord(c) > 127 for c in token):
                    emoji_missing += 1
                else:
                    regular_missing += 1
        
        return {
            "openstamp_count": len(openstamp_tokens),
            "database_count": len(db_tokens),
            "exact_matches": len(exact_matches),
            "openstamp_only": len(openstamp_only),
            "database_only": len(db_only),
            "case_insensitive_matches": len(case_insensitive_matches),
            "truly_missing_from_db": len(openstamp_only_case_insensitive),
            "missing_emoji_tokens": emoji_missing,
            "missing_regular_tokens": regular_missing
        }


def main():
    """Main entry point."""
    try:
        analyzer = OpenStampDBMismatchAnalyzer()
        result = analyzer.run_analysis()
        print(f"\n📊 Analysis complete: {result}")
        
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 