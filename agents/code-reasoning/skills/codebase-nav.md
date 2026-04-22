---
name: codebase-nav
description: Semantic codebase search — find where concepts are implemented using natural language queries
tags: [code-understanding, search, navigation]
---

# Codebase Navigator

Search the codebase using natural language queries like "where does authentication happen?"

## Workflow

1. Expand query into related keywords using concept mapping
2. Search codebase for all keyword matches
3. Score results by relevance (definitions > references, source > test)
4. Group by concept and file
5. Present ranked results with snippets

## Usage

```
/nav where does authentication happen?
/nav how are errors handled in the API layer?
/nav Redis caching patterns
/nav payment flow entry point
```

## Concepts Understood
authentication, authorization, database, caching, logging, testing, error_handling, api, security, deployment, messaging, payment, configuration, validation, monitoring
