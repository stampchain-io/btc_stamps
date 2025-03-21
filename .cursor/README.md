# Cursor Rules for Bitcoin Stamps

This directory contains rules for the Cursor IDE to more effectively work with the Bitcoin Stamps codebase. The rules help AI tools understand the codebase structure, important concepts, and relationships between components.

## Directory Structure

- `.cursor/rules/`: Contains all the rules files organized by component
  - `indexer.json`: Rules for the indexer component
  - `protocols.json`: Rules for understanding protocol specifications
  - `database.json`: Rules for database operations
  - `architecture.json`: Rules for overall architecture
  - `rust-parser.json`: Rules specific to the Rust parser component

## When to Update Rules

Update these rules when:
1. Introducing new components or major features
2. Changing architectural patterns
3. Modifying protocol specifications
4. Updating database schemas
5. Adding new documentation

## Benefits

- Consistent AI understanding of the codebase
- Better-targeted code suggestions
- More accurate documentation generation
- Easier onboarding for new contributors