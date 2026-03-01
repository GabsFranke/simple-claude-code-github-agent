# PR Review Flow with Subagents

## Overview

When a pull request is opened, the system performs a comprehensive multi-agent review using specialized subagents.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    PR Opened on GitHub                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Webhook Receives Event                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Message Published to Redis Queue                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           Worker Picks Up Message (auto_review=true)         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Main Agent (Coordinator) Spawned                │
│                   Claude Code CLI                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Read PR and Analyze Changes (Step 1)                │
│          - Get PR diff and details                           │
│          - Assess scope and type of changes                  │
│          - Decide which agents are needed                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────┴───────────────┐
         │  Spawn Selected Subagents     │
         │  (0-4 agents based on need)   │
         └───────────────┬───────────────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         │               │               │               │
         ▼               ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│Architecture │ │  Security   │ │ Bug Hunter  │ │Code Quality │
│  Reviewer   │ │  Reviewer   │ │             │ │  Reviewer   │
│  (if needed)│ │ (if needed) │ │ (if needed) │ │ (if needed) │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │
       │ Design        │ Vulnerabilities│ Bugs & Edge  │ Style &
       │ Patterns      │ Auth Issues   │ Cases        │ Maintainability
       │ SOLID         │ Data Exposure │ Error        │ Documentation
       │ Coupling      │ Injection     │ Handling     │ Complexity
       │               │               │               │
       └───────────────┴───────────────┴───────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Coordinator Collects JSON Results                   │
│          - Parses findings from each subagent                │
│          - Prioritizes by severity (Critical > High > Med)   │
│          - Groups by category                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Post Summary Comment (Step 1)                   │
│              - Overall assessment                            │
│              - Findings by category                          │
│              - Issue counts by severity                      │
│              - Positive notes                                │
│              Tool: add_issue_comment                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                    ┌────┴────┐
                    │ Issues? │
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼ Yes                 ▼ No
┌─────────────────────────┐  ┌──────────────┐
│  Create Pending Review  │  │   Done ✓     │
│  (Step 2a)              │  └──────────────┘
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│         Add Inline Comments Sequentially (Step 2b)           │
│         - Top 15-20 priority issues                          │
│         - Format: **[Severity] [Category]**: Issue           │
│         - Include explanation and suggestion                 │
│         Tool: add_comment_to_pending_review (sequential)     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Submit Review (Step 2c)                         │
│              - event: COMMENT or REQUEST_CHANGES             │
│              - Brief summary                                 │
│              Tool: pull_request_review_write                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Developer Sees Review on GitHub                 │
│              - Summary comment in conversation               │
│              - Inline comments on specific lines             │
└─────────────────────────────────────────────────────────────┘
```

## Subagent Outputs

Each subagent returns structured JSON:

### Architecture Reviewer
```json
{
  "findings": [
    {
      "file": "src/services/payment.ts",
      "line": 42,
      "severity": "medium",
      "category": "architecture",
      "issue": "Tight coupling between modules",
      "explanation": "Direct dependency creates tight coupling",
      "suggestion": "Consider using dependency injection",
      "impact": "Makes testing harder"
    }
  ],
  "summary": "Overall architectural assessment",
  "design_patterns_used": ["Factory", "Observer"],
  "concerns": ["Increased coupling"],
  "recommendations": ["Extract shared logic to service"]
}
```

### Security Reviewer
```json
{
  "findings": [
    {
      "file": "src/api/users.ts",
      "line": 15,
      "severity": "critical",
      "category": "security",
      "vulnerability_type": "SQL Injection",
      "issue": "Unsanitized user input in query",
      "explanation": "User input directly concatenated",
      "suggestion": "Use parameterized queries",
      "cwe": "CWE-89"
    }
  ],
  "summary": "Security assessment",
  "critical_count": 1,
  "high_count": 0,
  "overall_risk": "high"
}
```

### Bug Hunter
```json
{
  "findings": [
    {
      "file": "src/utils/parser.ts",
      "line": 28,
      "severity": "high",
      "category": "bug-risk",
      "issue": "Potential null pointer dereference",
      "explanation": "Variable could be null when accessed",
      "suggestion": "Add null check: if (!user) return;"
    }
  ],
  "summary": "Found 3 potential bugs",
  "risk_assessment": "Medium risk overall"
}
```

### Code Quality Reviewer
```json
{
  "findings": [
    {
      "file": "src/components/Form.tsx",
      "line": 55,
      "severity": "low",
      "category": "code-quality",
      "issue": "Function is too complex (20 lines)",
      "suggestion": "Break into smaller functions"
    }
  ],
  "summary": "Code quality is good overall",
  "positive_notes": ["Good TypeScript types", "Clear naming"]
}
```

## Benefits

1. **Intelligent Delegation**: Only uses agents that are relevant to the changes
2. **Efficient Reviews**: Small PRs get quick reviews, complex PRs get thorough analysis
3. **Focused Expertise**: Each subagent specializes in their domain
4. **Structured Output**: JSON format enables easy parsing and prioritization
5. **Consistent Quality**: Same thorough review process for similar changes
6. **Actionable Feedback**: Specific suggestions with code examples
7. **Cost Effective**: Doesn't waste tokens on unnecessary reviews

## Customization

Adjust review behavior via repository's `CLAUDE.md`:

```markdown
# Agent Instructions

For code reviews:
- Prioritize security findings above all else
- Be extra strict on error handling in payment module
- Ignore style issues in legacy code (src/legacy/)
- Always check for proper TypeScript types
```

## Performance

- **Subagent spawn time**: ~2-5 seconds per subagent
- **Parallel execution**: All 4 run simultaneously
- **Analysis time**: Depends on PR size (1-5 minutes typical)
- **Total review time**: 2-8 minutes for most PRs

## Observability

When Langfuse is enabled, you can see:
- Each subagent execution as a nested span
- Time spent in each subagent
- Findings from each subagent
- Coordinator's synthesis logic
- Final review output

Access at: http://localhost:7500
