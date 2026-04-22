"""CLI completions and help command — extracted from cli.py."""

from __future__ import annotations

import logging
import os
import sys

from .cli_helpers import _colors

logger = logging.getLogger("code_agents.cli.cli_completions")


def _get_commands() -> dict:
    """Lazy import COMMANDS to avoid circular import."""
    from .cli import COMMANDS
    return COMMANDS

_AGENT_NAMES_FOR_COMPLETION = [
    "agent-router", "argocd-verify", "auto-pilot", "code-reasoning",
    "code-reviewer", "code-tester", "code-writer", "explore", "git-ops",
    "jenkins-cicd", "jira-ops", "pipeline-orchestrator",
    "qa-regression", "redash-query", "test-coverage",
]

# Subcommands for commands that take them
_SUBCOMMANDS = {
    "repos":    ["add", "remove"],
    "rules":    ["list", "create", "edit", "delete"],
    "pipeline": ["start", "status", "advance", "rollback"],
    "start":    ["--fg", "--foreground"],
    "init":     ["--profile", "--backend", "--server", "--jenkins", "--argocd", "--jira", "--kibana", "--grafana", "--redash", "--elastic", "--atlassian", "--testing", "--build", "--k8s", "--notifications", "--slack", "--extensions"],
    "rules create": ["--global", "--agent"],
    "rules list": ["--agent"],
    "incident": ["--rca", "--save"],
    "deadcode":  ["--language", "--json"],
    "dead-code-eliminate": ["--apply", "--dry-run", "--json"],
    "security":  ["--json", "--category"],
    "audit":     ["--vuln", "--licenses", "--outdated", "--json"],
    "commit":   ["--auto", "--dry-run"],
    "config-diff": ["--json"],
    "flags":    ["--stale", "--matrix", "--json"],
    "release":  ["--dry-run", "--skip-deploy", "--skip-jira", "--skip-tests"],
    "oncall-report": ["--days", "--save", "--slack"],
    "onboard":  ["--save", "--full"],
    "sprint-velocity": ["--sprints", "--json"],
    "sprint-report": ["--days", "--save", "--slack"],
    "coverage-boost": ["--dry-run", "--target", "--commit"],
    "gen-tests": ["--verify", "--dry-run", "--max", "--all"],
    "watch": ["--lint-only", "--test-only", "--no-fix", "--interval"],
    "qa-suite": ["--analyze", "--write", "--commit"],
    "apidoc":   ["--markdown", "--openapi", "--json"],
    "api-docs": ["--format", "--output"],
    "perf-baseline": ["--compare", "--show", "--clear", "--iterations"],
    "chat":     _AGENT_NAMES_FOR_COMPLETION,
    "complexity": ["--language", "--json"],
    "techdebt":  ["--json"],
    "tech-debt": ["--json", "--save", "--trend"],
    "changelog": ["--write", "--version"],
    "changelog-gen": ["--format", "--output"],
    "watchdog":  ["--minutes"],
    "auto-review": [],
    "pre-push":  ["install"],
    "pre-push-check": [],
    "plugin":    ["list", "build", "install", "test", "dev", "watch", "status", "open", "publish", "vscode", "intellij", "chrome", "all"],
    "readme":    [],
    "slack":     ["test", "send", "status", "channels", "help"],
    "cost":      ["--daily", "--monthly", "--yearly", "--all", "--session", "--model", "--agent", "--export"],
    "undo":      ["--list", "--all", "--dry-run"],
    "skill":     ["list", "search", "install", "remove", "info"],
    "voice":     ["--continuous"],
    "pair":      ["--watch-path", "--interval", "--quiet"],
    # Productivity features
    "pr-describe": ["--base", "--format", "--no-reviewers", "--no-risk"],
    "postmortem": ["--from", "--to", "--service", "--format"],
    "postmortem-gen": ["--incident", "--time-range", "--title", "--format"],
    "dep-upgrade": ["--package", "--all", "--execute"],
    "review-buddy": ["--all", "--fix"],
    "db-migrate": ["--type", "--execute", "--preview"],
    "oncall-summary": ["--hours", "--channel", "--log"],
    "test-impact": ["--base", "--run"],
    "runbook": ["--list", "--execute"],
    "sprint-dashboard": ["--days", "--format"],
    "explain": [],
    "explain-code": ["--function", "--fn"],
    "corrections": ["list", "clear"],
    "mindmap": ["--format", "--depth", "--focus", "--output"],
    "review": ["--base", "--files", "--fix", "--category", "--json"],
    "migrate-tracing": ["--scan", "--apply", "--dry-run", "--rollback", "--language", "--exporter"],
    "txn-flow": ["--order-id", "--env", "--from-code", "--format"],
    "impact": ["--upgrade", "--check", "--apply"],
    "index": ["--force", "--stats"],
    "workspace": ["add", "remove", "list", "status", "cross-deps", "pr"],
    "install-hooks": ["--uninstall", "--status"],
    "hook-run": ["pre-commit", "pre-push"],
    "pci-scan": ["--format", "--output", "--severity"],
    "owasp-scan": ["--format", "--output", "--severity"],
    "replay": ["list", "show", "play", "fork", "delete", "search", "--limit", "--delay"],
    "audit-idempotency": ["--severity", "--format"],
    "tail": ["--service", "--env", "--index", "--level", "--interval"],
    "validate-states": ["--format"],
    "acquirer-health": ["--env", "--window", "--format", "--logs"],
    "profiler": ["--command", "--top", "--format"],
    "translate": ["--to", "--output"],
    "schema": ["--database", "--schema", "--format", "--sql-file", "--output"],
    "dashboard": ["--json", "--no-prs", "--no-tests"],
    "retry-audit": ["--severity", "--format"],
    "recon": ["--orders", "--settlements", "--format"],
    "load-test": ["--format", "--scenario", "--output"],
    "settlement": ["--file", "--format", "--compare", "--output"],
    "bg": ["list", "stop", "stop-all", "view", "clean"],
    "batch": ["--instruction", "--files", "--pattern", "--dry-run", "--parallel"],
    "ci-heal": ["--build", "--source", "--max-attempts", "--dry-run", "--log-file", "--url"],
    "ci-run": ["--json", "--fail-on", "--list", "fix-lint", "gen-tests", "update-docs", "review", "security-scan", "pci-scan", "owasp-scan", "dead-code", "audit"],
    "mutate-test": ["--target", "--max", "--timeout", "--format"],
    "pr-respond": ["--pr", "--auto-fix", "--no-fix", "--dry-run"],
    "screenshot": ["--image", "--framework", "--description", "--output"],
    "spec-validate": ["--spec", "--jira", "--prd", "--format"],
    "smell": ["--json"],
    "imports": ["--fix", "--json"],
    "adr": ["list", "--decision", "--context", "--alternatives", "--status"],
    "clones": ["--threshold", "--min-tokens", "--json"],
    "naming-audit": ["--json"],
    "encryption-audit": ["--format", "--output", "--severity"],
    "vuln-chain": ["--format", "--output", "--severity"],
    "input-audit": ["--format", "--output", "--severity"],
    "rate-limit-audit": ["--format", "--output", "--severity"],
    "privacy-scan": ["--regulation", "--format", "--output", "--severity"],
    "compliance-report": ["--standard", "--format", "--output"],
    "add-types": ["--path", "--dry-run", "--scan", "--json"],
    "comment-audit": ["--json", "--target", "--category"],
    "secret-rotation": ["--max-age", "--json", "--runbook"],
    "acl-matrix": ["--format", "--output"],
    "session-audit": ["--format", "--output", "--severity"],
    "archaeology": ["--function", "--fn", "--json"],
    "perf-proof": ["--command", "--iterations", "--json"],
    "contract-test": ["--format", "--output", "--target", "--json"],
    "self-bench": ["--tasks", "--json", "--trend", "--save"],
    "lang-migrate": ["--source", "--to", "--output"],
    "preview": ["--port"],
    "full-audit": ["--quick", "--ci", "--gates-only", "--trend", "--category", "--format", "--output"],
    "snippet": ["search", "save", "list", "delete", "show", "--file", "--code", "--language", "--tags", "--description", "--tag"],
    "env-diff": ["--json", "--list"],
    "ownership": ["--generate-codeowners", "--silos", "--json", "--output"],
    "velocity-predict": ["--committed", "--json"],
    "pr-split": ["--base", "--json"],
    "license-audit": ["--sbom", "--json", "--format"],
    "validate-config": ["--json"],
    "release-notes": ["--format", "--output"],
    "prop-test": ["--function", "--fn"],
    "test-style": ["--analyze", "--generate"],
    "visual-test": ["--url", "--name", "--compare", "--list", "--delete"],
    "browse": ["--url", "--extract-api", "--links"],
    "team-kb": ["list", "add", "get", "search", "delete", "--content", "--author"],
    "onboard-tour": [],
}


def _generate_zsh_completion() -> str:
    """Generate zsh completion script for code-agents."""
    cmds = sorted(_get_commands().keys())
    cmd_list = " ".join(cmds) + " help"
    agents = " ".join(_AGENT_NAMES_FOR_COMPLETION)

    # Build agent list as individual zsh array entries
    agents_zsh = " ".join(f"'{a}'" for a in _AGENT_NAMES_FOR_COMPLETION)

    return f'''#compdef code-agents
# Zsh completion for code-agents CLI
# Install: code-agents completions --zsh >> ~/.zshrc

_code_agents() {{
    local -a commands
    commands=(
        'init:Initialize code-agents in current repo'
        'migrate:Migrate legacy .env to centralized config'
        'rules:Manage agent rules (list/create/edit/delete)'
        'start:Start the server'
        'restart:Restart the server'
        'chat:Interactive chat with agents'
        'shutdown:Shutdown the server'
        'status:Check server health and config'
        'agents:List all available agents'
        'plugin:Manage IDE extensions (build/install/test/publish)'
        'readme:Display README in terminal'
        'config:Show current configuration'
        'doctor:Diagnose common issues'
        'logs:Tail the log file'
        'diff:Show git diff between branches'
        'branches:List git branches'
        'test:Run tests on the target repo'
        'review:Review code changes with AI'
        'pipeline:Manage CI/CD pipeline'
        'setup:Full interactive setup wizard'
        'curls:Show API curl commands'
        'version:Show version info'
        'help:Show help'
        'standup:Generate AI standup from git activity'
        'oncall-report:Generate on-call handoff report'
        'incident:Investigate a service incident (runbook + RCA)'
        'deadcode:Find dead code (unused imports, functions, endpoints)'
        'dead-code-eliminate:Cross-file dead code detection + safe removal'
        'commit:Smart commit — conventional message from staged diff'
        'config-diff:Compare configs across environments'
        'flags:List feature flags in codebase'
        'onboard:Generate onboarding guide for new developers'
        'coverage-boost:Auto-boost test coverage — scan, analyze, generate tests'
        'gen-tests:AI test generation — auto-delegate to code-tester, write & verify'
        'watch:Watch mode — auto-lint, auto-test, auto-fix on file save'
        'security:OWASP security scan — find vulnerabilities in code'
        'audit:Audit dependencies for CVEs, licenses, outdated versions'
        'sprint-velocity:Track sprint velocity across sprints from Jira'
        'api-check:Compare API endpoints with last release for breaking changes'
        'sprint-report:Generate sprint summary from Jira + git + builds'
        'pr-preview:Preview what a PR would look like (diff, risk, tests)'
        'apidoc:Generate API documentation from source code'
        'api-docs:Automated API docs — scan routes, generate OpenAPI/Markdown/HTML'
        'perf-baseline:Record or compare performance baseline'
        'completions:Generate shell completion script'
        'complexity:Analyze code complexity (cyclomatic, nesting depth)'
        'techdebt:Scan for tech debt (TODOs, deprecated, skipped tests)'
        'changelog:Generate changelog from conventional commits'
        'changelog-gen:Generate changelog with PR enrichment between refs'
        'env-health:Check environment health dashboard'
        'morning:Morning autopilot — git pull, build, Jira, tests'
        'pre-push-check:Pre-push checklist — tests, secrets, lint'
        'pre-push:Pre-push checklist (install hook or run checks)'
        'watchdog:Post-deploy watchdog — monitor error rate'
        'auto-review:Automated code review — diff analysis + AI'
        'pr-describe:Generate PR description from branch diff'
        'postmortem:Generate incident postmortem from time range'
        'postmortem-gen:Auto-generate structured postmortem with timeline and root cause'
        'dep-upgrade:Scan and upgrade outdated dependencies'
        'review-buddy:Pre-push code review against conventions'
        'db-migrate:Generate DB migration from plain English'
        'oncall-summary:Summarize on-call alerts + generate standup'
        'test-impact:Analyze which tests are impacted by changes'
        'runbook:Execute runbooks with safety gates'
        'sprint-dashboard:Sprint velocity dashboard with cycle time'
        'explain:Ask questions about the codebase'
        'install-hooks:Install AI-powered git hooks (pre-commit, pre-push)'
        'hook-run:Run git hook analysis (called by hook scripts)'
        'replay:Agent replay / time travel debugging'
        'translate:Translate code between languages (regex-based scaffolding)'
        'load-test:Generate load test scripts (k6, Locust, JMeter) from API endpoints'
        'ci-heal:CI pipeline self-healing — diagnose failures, apply fixes, re-trigger'
        'ci-run:Headless CI mode — run agent tasks non-interactively'
        'pr-respond:Respond to PR review comments — address feedback, push fixes, reply in-thread'
        'smell:Code smell detector — god classes, long methods, deep nesting, data clumps'
        'adr:Generate Architecture Decision Records (ADRs)'
        'clones:Detect code clones (duplicated code blocks)'
        'naming-audit:Audit naming conventions — mixed styles, abbreviations'
        'add-types:Add type annotations to untyped Python functions'
        'comment-audit:Audit code comments — obvious, stale, TODO without ticket'
        'secret-rotation:Track secret rotation — find stale secrets, generate runbooks'
        'acl-matrix:Generate ACL matrix — roles, endpoints, escalation paths'
        'session-audit:Audit session management — JWT expiry, cookies, fixation'
        'archaeology:Code archaeology — trace origin and intent behind code'
        'perf-proof:Performance benchmark with statistical proof'
        'contract-test:Generate API contract tests (Pact/JSON Schema)'
        'self-bench:Self-benchmark agent quality — review, test, bug detection'
        'lang-migrate:Migrate a module to another programming language'
        'preview:Live preview server — serve static files with auto-reload'
        'snippet:Smart snippet library — search, save, list, delete snippets'
        'env-diff:Compare environment configs (.env.dev vs .env.staging)'
        'ownership:Code ownership map — git blame, bus factor, CODEOWNERS'
        'velocity-predict:Sprint velocity predictor — capacity from git history'
        'prop-test:Generate Hypothesis property-based tests from source code'
        'test-style:Analyze project test style or generate style-matching tests'
        'visual-test:Visual regression testing — capture and compare page snapshots'
        'browse:Browser agent — fetch page, extract text, scrape API docs'
        'team-kb:Team knowledge base — add, search, list, delete entries'
        'onboard-tour:Generate onboarding tour for new developers'
    )

    local -a rules_subcmds
    rules_subcmds=('list:List active rules' 'create:Create a new rule' 'edit:Edit a rule file' 'delete:Delete a rule file')

    local -a pipeline_subcmds
    pipeline_subcmds=('start:Start pipeline' 'status:Show pipeline status' 'advance:Advance pipeline step' 'rollback:Rollback deployment')

    if (( CURRENT == 2 )); then
        _describe 'command' commands
    elif (( CURRENT == 3 )); then
        case $words[2] in
            init)
                compadd -- '--profile' '--backend' '--server' '--jenkins' '--argocd' '--jira' '--kibana' '--grafana' '--redash' '--elastic' '--atlassian' '--testing' '--build' '--k8s' '--notifications'
                ;;
            rules)
                _describe 'subcommand' rules_subcmds
                ;;
            pipeline)
                _describe 'subcommand' pipeline_subcmds
                ;;
            chat)
                compadd -- {agents_zsh}
                ;;
            start)
                compadd -- '--fg' '--foreground'
                ;;
            commit)
                compadd -- '--auto' '--dry-run'
                ;;
            oncall-report)
                compadd -- '--days' '--save' '--slack'
                ;;
            flags)
                compadd -- '--stale' '--matrix' '--json'
                ;;
            onboard)
                compadd -- '--save' '--full'
                ;;
            coverage-boost)
                compadd -- '--dry-run' '--target' '--commit'
                ;;
            gen-tests)
                compadd -- '--verify' '--dry-run' '--max' '--all'
                ;;
            watch)
                compadd -- '--lint-only' '--test-only' '--no-fix' '--interval'
                ;;
            security)
                compadd -- '--json' '--category'
                ;;
            audit)
                compadd -- '--vuln' '--licenses' '--outdated' '--json'
                ;;
            sprint-velocity)
                compadd -- '--sprints' '--json'
                ;;
            sprint-report)
                compadd -- '--days' '--save' '--slack'
                ;;
            apidoc)
                compadd -- '--markdown' '--openapi' '--json'
                ;;
            api-docs)
                compadd -- '--format' '--output'
                ;;
            perf-baseline)
                compadd -- '--compare' '--show' '--clear' '--iterations'
                ;;
            complexity)
                compadd -- '--language' '--json'
                ;;
            techdebt)
                compadd -- '--json'
                ;;
            changelog)
                compadd -- '--write' '--version'
                ;;
            changelog-gen)
                compadd -- '--format' '--output'
                ;;
            watchdog)
                compadd -- '--minutes'
                ;;
            pre-push)
                compadd -- 'install'
                ;;
            pr-describe)
                compadd -- '--base' '--format' '--no-reviewers' '--no-risk'
                ;;
            postmortem)
                compadd -- '--from' '--to' '--service' '--format'
                ;;
            postmortem-gen)
                compadd -- '--incident' '--time-range' '--title' '--format'
                ;;
            dep-upgrade)
                compadd -- '--package' '--all' '--execute'
                ;;
            review-buddy)
                compadd -- '--all' '--fix'
                ;;
            db-migrate)
                compadd -- '--type' '--execute' '--preview'
                ;;
            oncall-summary)
                compadd -- '--hours' '--channel' '--log'
                ;;
            test-impact)
                compadd -- '--base' '--run'
                ;;
            runbook)
                compadd -- '--list' '--execute'
                ;;
            sprint-dashboard)
                compadd -- '--days' '--format'
                ;;
            install-hooks)
                compadd -- '--uninstall' '--status'
                ;;
            hook-run)
                compadd -- 'pre-commit' 'pre-push'
                ;;
            replay)
                compadd -- 'list' 'show' 'play' 'fork' 'delete' 'search'
                ;;
            translate)
                compadd -- '--to' '--output'
                ;;
            load-test)
                compadd -- '--format' '--scenario' '--output'
                ;;
            ci-heal)
                compadd -- '--build' '--source' '--max-attempts' '--dry-run' '--log-file' '--url'
                ;;
            ci-run)
                compadd -- '--json' '--fail-on' '--list' 'fix-lint' 'gen-tests' 'update-docs' 'review' 'security-scan' 'pci-scan' 'owasp-scan' 'dead-code' 'audit'
                ;;
            pr-respond)
                compadd -- '--pr' '--auto-fix' '--no-fix' '--dry-run'
                ;;
            smell)
                compadd -- '--json'
                ;;
            adr)
                compadd -- 'list' '--decision' '--context' '--alternatives' '--status'
                ;;
            clones)
                compadd -- '--threshold' '--min-tokens' '--json'
                ;;
            naming-audit)
                compadd -- '--json'
                ;;
            add-types)
                compadd -- '--path' '--dry-run' '--scan' '--json'
                ;;
            comment-audit)
                compadd -- '--json' '--target' '--category'
                ;;
            secret-rotation)
                compadd -- '--max-age' '--json' '--runbook'
                ;;
            acl-matrix)
                compadd -- '--format' '--output'
                ;;
            session-audit)
                compadd -- '--format' '--output' '--severity'
                ;;
            archaeology)
                compadd -- '--function' '--fn' '--json'
                ;;
            perf-proof)
                compadd -- '--command' '--iterations' '--json'
                ;;
            contract-test)
                compadd -- '--format' '--output' '--target' '--json'
                ;;
            self-bench)
                compadd -- '--tasks' '--json' '--trend' '--save'
                ;;
            snippet)
                compadd -- 'search' 'save' 'list' 'delete' 'show' '--file' '--code' '--language' '--tags' '--tag'
                ;;
            env-diff)
                compadd -- '--json' '--list'
                ;;
            ownership)
                compadd -- '--generate-codeowners' '--silos' '--json' '--output'
                ;;
            velocity-predict)
                compadd -- '--committed' '--json'
                ;;
            prop-test)
                compadd -- '--function' '--fn'
                ;;
            test-style)
                compadd -- '--analyze' '--generate'
                ;;
            visual-test)
                compadd -- '--url' '--name' '--compare' '--list' '--delete'
                ;;
            browse)
                compadd -- '--url' '--extract-api' '--links'
                ;;
            team-kb)
                compadd -- 'list' 'add' 'get' 'search' 'delete' '--content' '--author'
                ;;
        esac
    elif (( CURRENT == 4 )); then
        case "$words[2] $words[3]" in
            "rules create"|"rules list")
                compadd -- '--global' '--agent'
                ;;
        esac
    elif (( CURRENT >= 4 )); then
        # After --agent anywhere in the line, complete agent names
        if [[ "${{words[CURRENT-1]}}" == "--agent" ]]; then
            compadd -- {agents_zsh}
        fi
    fi
}}

compdef _code_agents code-agents
'''


def _generate_bash_completion() -> str:
    """Generate bash completion script for code-agents."""
    cmds = sorted(_get_commands().keys())
    cmd_list = " ".join(cmds) + " help completions"

    return f'''# Bash completion for code-agents CLI
# Install: code-agents completions --bash >> ~/.bashrc

_code_agents_completions() {{
    local cur prev commands
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    commands="{cmd_list}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    elif [[ $COMP_CWORD -eq 2 ]]; then
        case "$prev" in
            init)
                COMPREPLY=( $(compgen -W "--profile --backend --server --jenkins --argocd --jira --kibana --grafana --redash --elastic --atlassian --testing --build --k8s --notifications" -- "$cur") )
                ;;
            rules)
                COMPREPLY=( $(compgen -W "list create edit delete" -- "$cur") )
                ;;
            pipeline)
                COMPREPLY=( $(compgen -W "start status advance rollback" -- "$cur") )
                ;;
            chat)
                COMPREPLY=( $(compgen -W "agent-router argocd-verify auto-pilot code-reasoning code-reviewer code-tester code-writer explore git-ops jenkins-cicd jira-ops pipeline-orchestrator qa-regression redash-query test-coverage" -- "$cur") )
                ;;
            start)
                COMPREPLY=( $(compgen -W "--fg --foreground" -- "$cur") )
                ;;
            oncall-report)
                COMPREPLY=( $(compgen -W "--days --save --slack" -- "$cur") )
                ;;
            flags)
                COMPREPLY=( $(compgen -W "--stale --matrix --json" -- "$cur") )
                ;;
            commit)
                COMPREPLY=( $(compgen -W "--auto --dry-run" -- "$cur") )
                ;;
            onboard)
                COMPREPLY=( $(compgen -W "--save --full" -- "$cur") )
                ;;
            coverage-boost)
                COMPREPLY=( $(compgen -W "--dry-run --target --commit" -- "$cur") )
                ;;
            gen-tests)
                COMPREPLY=( $(compgen -W "--verify --dry-run --max --all" -- "$cur") )
                ;;
            watch)
                COMPREPLY=( $(compgen -W "--lint-only --test-only --no-fix --interval" -- "$cur") )
                ;;
            security)
                COMPREPLY=( $(compgen -W "--json --category" -- "$cur") )
                ;;
            audit)
                COMPREPLY=( $(compgen -W "--vuln --licenses --outdated --json" -- "$cur") )
                ;;
            sprint-velocity)
                COMPREPLY=( $(compgen -W "--sprints --json" -- "$cur") )
                ;;
            sprint-report)
                COMPREPLY=( $(compgen -W "--days --save --slack" -- "$cur") )
                ;;
            apidoc)
                COMPREPLY=( $(compgen -W "--markdown --openapi --json" -- "$cur") )
                ;;
            api-docs)
                COMPREPLY=( $(compgen -W "--format --output" -- "$cur") )
                ;;
            perf-baseline)
                COMPREPLY=( $(compgen -W "--compare --show --clear --iterations" -- "$cur") )
                ;;
            complexity)
                COMPREPLY=( $(compgen -W "--language --json" -- "$cur") )
                ;;
            techdebt)
                COMPREPLY=( $(compgen -W "--json" -- "$cur") )
                ;;
            changelog)
                COMPREPLY=( $(compgen -W "--write --version" -- "$cur") )
                ;;
            changelog-gen)
                COMPREPLY=( $(compgen -W "--format --output" -- "$cur") )
                ;;
            watchdog)
                COMPREPLY=( $(compgen -W "--minutes" -- "$cur") )
                ;;
            pre-push)
                COMPREPLY=( $(compgen -W "install" -- "$cur") )
                ;;
            pr-describe)
                COMPREPLY=( $(compgen -W "--base --format --no-reviewers --no-risk" -- "$cur") )
                ;;
            postmortem)
                COMPREPLY=( $(compgen -W "--from --to --service --format" -- "$cur") )
                ;;
            postmortem-gen)
                COMPREPLY=( $(compgen -W "--incident --time-range --title --format" -- "$cur") )
                ;;
            dep-upgrade)
                COMPREPLY=( $(compgen -W "--package --all --execute" -- "$cur") )
                ;;
            review-buddy)
                COMPREPLY=( $(compgen -W "--all --fix" -- "$cur") )
                ;;
            db-migrate)
                COMPREPLY=( $(compgen -W "--type --execute --preview" -- "$cur") )
                ;;
            oncall-summary)
                COMPREPLY=( $(compgen -W "--hours --channel --log" -- "$cur") )
                ;;
            test-impact)
                COMPREPLY=( $(compgen -W "--base --run" -- "$cur") )
                ;;
            runbook)
                COMPREPLY=( $(compgen -W "--list --execute" -- "$cur") )
                ;;
            sprint-dashboard)
                COMPREPLY=( $(compgen -W "--days --format" -- "$cur") )
                ;;
            install-hooks)
                COMPREPLY=( $(compgen -W "--uninstall --status" -- "$cur") )
                ;;
            hook-run)
                COMPREPLY=( $(compgen -W "pre-commit pre-push" -- "$cur") )
                ;;
            replay)
                COMPREPLY=( $(compgen -W "list show play fork delete search" -- "$cur") )
                ;;
            translate)
                COMPREPLY=( $(compgen -W "--to --output" -- "$cur") )
                ;;
            load-test)
                COMPREPLY=( $(compgen -W "--format --scenario --output" -- "$cur") )
                ;;
            ci-heal)
                COMPREPLY=( $(compgen -W "--build --source --max-attempts --dry-run --log-file --url" -- "$cur") )
                ;;
            ci-run)
                COMPREPLY=( $(compgen -W "--json --fail-on --list fix-lint gen-tests update-docs review security-scan pci-scan owasp-scan dead-code audit" -- "$cur") )
                ;;
            pr-respond)
                COMPREPLY=( $(compgen -W "--pr --auto-fix --no-fix --dry-run" -- "$cur") )
                ;;
            smell)
                COMPREPLY=( $(compgen -W "--json" -- "$cur") )
                ;;
            adr)
                COMPREPLY=( $(compgen -W "list --decision --context --alternatives --status" -- "$cur") )
                ;;
            clones)
                COMPREPLY=( $(compgen -W "--threshold --min-tokens --json" -- "$cur") )
                ;;
            naming-audit)
                COMPREPLY=( $(compgen -W "--json" -- "$cur") )
                ;;
            add-types)
                COMPREPLY=( $(compgen -W "--path --dry-run --scan --json" -- "$cur") )
                ;;
            comment-audit)
                COMPREPLY=( $(compgen -W "--json --target --category" -- "$cur") )
                ;;
            secret-rotation)
                COMPREPLY=( $(compgen -W "--max-age --json --runbook" -- "$cur") )
                ;;
            acl-matrix)
                COMPREPLY=( $(compgen -W "--format --output" -- "$cur") )
                ;;
            session-audit)
                COMPREPLY=( $(compgen -W "--format --output --severity" -- "$cur") )
                ;;
            archaeology)
                COMPREPLY=( $(compgen -W "--function --fn --json" -- "$cur") )
                ;;
            perf-proof)
                COMPREPLY=( $(compgen -W "--command --iterations --json" -- "$cur") )
                ;;
            contract-test)
                COMPREPLY=( $(compgen -W "--format --output --target --json" -- "$cur") )
                ;;
            self-bench)
                COMPREPLY=( $(compgen -W "--tasks --json --trend --save" -- "$cur") )
                ;;
            snippet)
                COMPREPLY=( $(compgen -W "search save list delete show --file --code --language --tags --tag" -- "$cur") )
                ;;
            env-diff)
                COMPREPLY=( $(compgen -W "--json --list" -- "$cur") )
                ;;
            ownership)
                COMPREPLY=( $(compgen -W "--generate-codeowners --silos --json --output" -- "$cur") )
                ;;
            velocity-predict)
                COMPREPLY=( $(compgen -W "--committed --json" -- "$cur") )
                ;;
            prop-test)
                COMPREPLY=( $(compgen -W "--function --fn" -- "$cur") )
                ;;
            test-style)
                COMPREPLY=( $(compgen -W "--analyze --generate" -- "$cur") )
                ;;
            visual-test)
                COMPREPLY=( $(compgen -W "--url --name --compare --list --delete" -- "$cur") )
                ;;
            browse)
                COMPREPLY=( $(compgen -W "--url --extract-api --links" -- "$cur") )
                ;;
            team-kb)
                COMPREPLY=( $(compgen -W "list add get search delete --content --author" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 3 ]]; then
        case "${{COMP_WORDS[1]}} ${{COMP_WORDS[2]}}" in
            "rules create"|"rules list")
                COMPREPLY=( $(compgen -W "--global --agent" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 4 ]] && [[ "$prev" == "--agent" ]]; then
        COMPREPLY=( $(compgen -W "agent-router argocd-verify code-reasoning code-reviewer code-tester code-writer explore git-ops jenkins-cicd pipeline-orchestrator redash-query test-coverage" -- "$cur") )
    fi
}}

complete -F _code_agents_completions code-agents
'''


def cmd_completions(rest: list[str] | None = None):
    """Generate shell completion script."""
    rest = rest or []
    bold, green, yellow, red, cyan, dim = _colors()

    if "--zsh" in rest:
        print(_generate_zsh_completion())
    elif "--bash" in rest:
        print(_generate_bash_completion())
    elif "--install" in rest:
        # Auto-detect shell and install
        shell_rc = None
        if os.path.exists(os.path.expanduser("~/.zshrc")):
            shell_rc = os.path.expanduser("~/.zshrc")
            script = _generate_zsh_completion()
            marker = "# code-agents completion"
        elif os.path.exists(os.path.expanduser("~/.bashrc")):
            shell_rc = os.path.expanduser("~/.bashrc")
            script = _generate_bash_completion()
            marker = "# code-agents completion"
        else:
            print(red("  Could not detect shell config (~/.zshrc or ~/.bashrc)"))
            return

        # Check if already installed
        with open(shell_rc) as f:
            if marker in f.read():
                print(green(f"  ✓ Completions already installed in {shell_rc}"))
                return

        with open(shell_rc, "a") as f:
            f.write(f"\n{marker}\n")
            f.write(script)
            f.write(f"\n")

        print(green(f"  ✓ Completions installed in {shell_rc}"))
        print(dim(f"    Restart your terminal or run: source {shell_rc}"))
    else:
        print()
        print(bold("  Generate shell completion for code-agents"))
        print()
        print(f"    {cyan('code-agents completions --install')}    {dim('Auto-install to ~/.zshrc or ~/.bashrc')}")
        print(f"    {cyan('code-agents completions --zsh')}        {dim('Print zsh completion script')}")
        print(f"    {cyan('code-agents completions --bash')}       {dim('Print bash completion script')}")
        print()


def cmd_help():
    """Show comprehensive help with all commands organized by category."""
    bold, green, yellow, red, cyan, dim = _colors()
    p = print  # shorthand

    p()
    p(bold("  code-agents — AI-powered code agent platform (15 agents, 154 skills, 80+ commands)"))
    p(bold("  " + "=" * 75))
    p()
    p(bold("  USAGE:"))
    p(f"    code-agents {cyan('<command>')} [args] [options]")
    p()

    # ── Core ──
    p(bold("  CORE"))
    p()
    p(f"    {cyan('chat'):<30} Interactive chat with agents (15 specialists)")
    p(f"    {cyan('init'):<30} Initialize code-agents in current repo (smart wizard)")
    p(f"    {cyan('setup'):<30} Full interactive setup wizard (7 steps)")
    p(f"    {cyan('start'):<30} Start the server ({dim('--fg')} for foreground)")
    p(f"    {cyan('shutdown'):<30} Shutdown the server")
    p(f"    {cyan('restart'):<30} Restart server (shutdown + start)")
    p(f"    {cyan('status'):<30} Health check, version, agent count, integrations")
    p(f"    {cyan('doctor'):<30} Diagnose environment, backend, integrations, git, build")
    p(f"    {cyan('help'):<30} This help message")
    p(f"    {cyan('version'):<30} Show version info")
    p(f"    {cyan('config'):<30} Show current configuration (secrets masked)")
    p(f"    {cyan('agents'):<30} List all available agents with roles")
    p(f"    {cyan('logs'):<30} Tail the log file")
    p(f"    {cyan('update'):<30} Pull latest code + reinstall deps")
    p(f"    {cyan('migrate'):<30} Migrate legacy .env to centralized config")
    p(f"    {cyan('rules'):<30} Manage rules [list|create|edit|delete]")
    p(f"    {cyan('export'):<30} Export for Claude Code or Cursor [--claude-code|--cursor|--all]")
    p(f"    {cyan('plugin'):<30} Manage IDE extensions [list|build|install|test|publish]")
    p(f"    {cyan('completions'):<30} Shell tab-completion for zsh/bash (--install)")
    p()

    # ── Analysis ──
    p(bold("  ANALYSIS"))
    p()
    p(f"    {cyan('mindmap'):<30} Generate visual mindmap of the repository")
    p(f"    {cyan('explain-code'):<30} Explain a code block, function, or file with static analysis")
    p(f"    {cyan('explain'):<30} Ask questions about the codebase")
    p(f"    {cyan('smell'):<30} Code smell detector — god classes, long methods, deep nesting")
    p(f"    {cyan('tech-debt'):<30} Deep tech debt scan — TODOs, complexity, test gaps, deps")
    p(f"    {cyan('techdebt'):<30} Scan for tech debt (TODOs, deprecated, skipped tests)")
    p(f"    {cyan('clones'):<30} Detect code clones (duplicated code blocks)")
    p(f"    {cyan('deadcode'):<30} Find dead code — unused imports, functions, endpoints")
    p(f"    {cyan('dead-code-eliminate'):<30} Cross-file dead code detection + safe removal")
    p(f"    {cyan('complexity'):<30} Analyze code complexity (cyclomatic, nesting depth)")
    p(f"    {cyan('dashboard'):<30} Code health dashboard — tests, coverage, complexity, PRs")
    p(f"    {cyan('imports'):<30} Import optimizer — unused, circular, heavy, wildcard")
    p(f"    {cyan('flags'):<30} List feature flags in codebase")
    p(f"    {cyan('config-diff'):<30} Compare configs across environments")
    p(f"    {cyan('env-diff'):<30} Compare environment configs (.env.dev vs .env.staging)")
    p(f"    {cyan('ownership'):<30} Code ownership map — git blame, bus factor, CODEOWNERS")
    p(f"    {cyan('nav'):<30} Semantic codebase search — find where concepts are implemented")
    p(f"    {cyan('call-chain'):<30} Show full call tree (callers and callees) for a function")
    p(f"    {cyan('usage-trace'):<30} Find all usages of a symbol across the codebase")
    p(f"    {cyan('dep-graph'):<30} Dependency graph with Mermaid/DOT visualization")
    p(f"    {cyan('examples'):<30} Find code examples for a concept or library usage")
    p(f"    {cyan('git-story'):<30} Reconstruct the full story behind a line of code")
    p()

    # ── Code Quality ──
    p(bold("  CODE QUALITY"))
    p()
    p(f"    {cyan('review'):<30} AI code review with inline terminal diff")
    p(f"    {cyan('auto-review'):<30} Automated code review — diff analysis + AI review")
    p(f"    {cyan('review-fix'):<30} AI code review with auto-fix — review + fix + PR comments")
    p(f"    {cyan('review-buddy'):<30} Pre-push code review against conventions")
    p(f"    {cyan('add-types'):<30} Add type annotations to untyped Python functions")
    p(f"    {cyan('comment-audit'):<30} Audit code comments — obvious, stale, TODO without ticket")
    p(f"    {cyan('naming-audit'):<30} Audit naming conventions — mixed styles, abbreviations")
    p()

    # ── Testing ──
    p(bold("  TESTING"))
    p()
    p(f"    {cyan('test'):<30} Run tests on the target repo")
    p(f"    {cyan('gen-tests'):<30} AI test generation — auto-delegate to code-tester, write & verify")
    p(f"    {cyan('mutate-test'):<30} Mutation testing — inject faults, verify tests catch them")
    p(f"    {cyan('contract-test'):<30} Generate API contract tests (Pact/JSON Schema)")
    p(f"    {cyan('self-bench'):<30} Self-benchmark agent quality — review, test, bug detection")
    p(f"    {cyan('coverage'):<30} Lightweight coverage report (batch mode, memory-safe)")
    p(f"    {cyan('coverage-boost'):<30} Auto-boost test coverage — scan, analyze, generate tests")
    p(f"    {cyan('qa-suite'):<30} Generate QA regression test suite for the repo")
    p(f"    {cyan('test-impact'):<30} Analyze which tests are impacted by changes")
    p(f"    {cyan('perf-proof'):<30} Performance benchmark with statistical proof")
    p()

    # ── Security ──
    p(bold("  SECURITY"))
    p()
    p(f"    {cyan('security'):<30} OWASP security scan — find vulnerabilities in code")
    p(f"    {cyan('pci-scan'):<30} PCI-DSS compliance scanner for payment gateway code")
    p(f"    {cyan('owasp-scan'):<30} OWASP Top 10 security scanner")
    p(f"    {cyan('encryption-audit'):<30} Scan for weak encryption — MD5, DES, ECB, small keys")
    p(f"    {cyan('input-audit'):<30} Input validation coverage — find endpoints missing validation")
    p(f"    {cyan('session-audit'):<30} Audit session management — JWT expiry, cookies, fixation")
    p(f"    {cyan('acl-matrix'):<30} Generate ACL matrix — roles, endpoints, escalation paths")
    p(f"    {cyan('vuln-chain'):<30} Vulnerability dependency chain — trace CVEs through deps")
    p(f"    {cyan('secret-rotation'):<30} Track secret rotation — find stale secrets, generate runbooks")
    p(f"    {cyan('privacy-scan'):<30} Data privacy scanner — PII in logs, consent, GDPR/DPDP")
    p(f"    {cyan('compliance-report'):<30} Compliance report generator — PCI, SOC2, GDPR control mapping")
    p(f"    {cyan('rate-limit-audit'):<30} Audit endpoints for missing rate limiting")
    p(f"    {cyan('audit'):<30} Audit dependencies for CVEs, licenses, outdated")
    p()

    # ── Payment ──
    p(bold("  PAYMENT"))
    p()
    p(f"    {cyan('txn-flow'):<30} Visualize transaction flow from logs or code state machines")
    p(f"    {cyan('recon'):<30} Payment reconciliation debugger — orders vs settlements")
    p(f"    {cyan('audit-idempotency'):<30} Scan payment endpoints for idempotency key issues")
    p(f"    {cyan('validate-states'):<30} Validate transaction state machines in code")
    p(f"    {cyan('acquirer-health'):<30} Monitor payment acquirer success rates, latency, errors")
    p(f"    {cyan('retry-audit'):<30} Payment retry strategy analyzer — detect retry anti-patterns")
    p(f"    {cyan('settlement'):<30} Settlement file parser & validator")
    p(f"    {cyan('load-test'):<30} Generate load test scripts (k6, Locust, JMeter)")
    p()

    # ── DevOps ──
    p(bold("  DEVOPS"))
    p()
    p(f"    {cyan('tail'):<30} Live tail — stream logs with anomaly detection")
    p(f"    {cyan('pair'):<30} AI pair programming — watch files, suggest improvements")
    p(f"    {cyan('install-hooks'):<30} Install AI-powered git hooks (pre-commit, pre-push)")
    p(f"    {cyan('hook-run'):<30} Run git hook analysis (called by hook scripts)")
    p(f"    {cyan('ci-heal'):<30} CI pipeline self-healing — diagnose failures, apply fixes")
    p(f"    {cyan('ci-run'):<30} Headless CI mode — run agent tasks non-interactively")
    p(f"    {cyan('bg'):<30} Background agent manager — list, stop, view background tasks")
    p(f"    {cyan('profiler'):<30} Performance profiler — cProfile hotspots and optimization")
    p(f"    {cyan('migrate-tracing'):<30} Migrate legacy tracing to OpenTelemetry")
    p(f"    {cyan('pipeline'):<30} Manage CI/CD pipeline [start|status|advance|rollback]")
    p(f"    {cyan('release'):<30} Automate release process end-to-end")
    p(f"    {cyan('watch'):<30} Watch mode — auto-lint, auto-test, auto-fix on file save")
    p(f"    {cyan('watchdog'):<30} Post-deploy watchdog — monitor error rate after deploy")
    p(f"    {cyan('debug'):<30} Autonomous debug — reproduce, trace, root-cause, fix, verify")
    p(f"    {cyan('morning'):<30} Morning autopilot — git pull, build, Jira, tests, alerts")
    p(f"    {cyan('env-health'):<30} Check environment health (ArgoCD, Jenkins, Jira, Kibana)")
    p(f"    {cyan('preview'):<30} Live preview server — serve static files with auto-reload")
    p()

    # ── Documentation ──
    p(bold("  DOCUMENTATION"))
    p()
    p(f"    {cyan('api-docs'):<30} Automated API docs — scan routes, generate OpenAPI/Markdown/HTML")
    p(f"    {cyan('apidoc'):<30} Generate API documentation from source code")
    p(f"    {cyan('changelog'):<30} Generate changelog from conventional commits")
    p(f"    {cyan('changelog-gen'):<30} Generate changelog with PR enrichment between refs")
    p(f"    {cyan('adr'):<30} Generate Architecture Decision Records (ADRs)")
    p(f"    {cyan('postmortem'):<30} Generate incident postmortem from time range")
    p(f"    {cyan('postmortem-gen'):<30} Auto-generate structured postmortem with timeline + root cause")
    p(f"    {cyan('onboard'):<30} Generate onboarding guide for new developers")
    p(f"    {cyan('readme'):<30} Display README in terminal with rich formatting")
    p()

    # ── Git/PR ──
    p(bold("  GIT / PR"))
    p()
    p(f"    {cyan('commit'):<30} Smart commit — conventional message from staged diff")
    p(f"    {cyan('branches'):<30} List all branches, highlight current")
    p(f"    {cyan('diff'):<30} Show git diff between branches")
    p(f"    {cyan('pr-describe'):<30} Generate PR description from branch diff")
    p(f"    {cyan('pr-preview'):<30} Preview what a PR would look like (diff, risk, tests)")
    p(f"    {cyan('pr-respond'):<30} Respond to PR review comments — address feedback, push fixes")
    p(f"    {cyan('archaeology'):<30} Code archaeology — trace origin and intent behind code")
    p(f"    {cyan('pre-push'):<30} Pre-push checklist [install|check]")
    p()

    # ── Data ──
    p(bold("  DATA"))
    p()
    p(f"    {cyan('schema'):<30} Database schema visualizer — ER diagrams from DB or SQL files")
    p(f"    {cyan('impact'):<30} Dependency impact scanner — analyze upgrade risk")
    p(f"    {cyan('dep-upgrade'):<30} Scan and upgrade outdated dependencies")
    p(f"    {cyan('db-migrate'):<30} Generate DB migration from plain English")
    p()

    # ── Workspace ──
    p(bold("  WORKSPACE"))
    p()
    p(f"    {cyan('workspace'):<30} Multi-repo workspace [add|remove|list|status]")
    p(f"    {cyan('replay'):<30} Agent replay / time travel debugging")
    p(f"    {cyan('index'):<30} Build or inspect the RAG code index [--force|--stats]")
    p(f"    {cyan('translate'):<30} Translate code between languages (regex-based scaffolding)")
    p(f"    {cyan('lang-migrate'):<30} Migrate entire module to another language")
    p(f"    {cyan('batch'):<30} Batch operations — apply instruction across many files")
    p(f"    {cyan('screenshot'):<30} Screenshot-to-code — generate UI from screenshot or description")
    p(f"    {cyan('spec-validate'):<30} Validate spec/PRD/Jira requirements against implementation")
    p(f"    {cyan('sessions'):<30} List saved chat sessions")
    p(f"    {cyan('repos'):<30} List and manage registered repos")
    p()

    # ── Incident & Reports ──
    p(bold("  INCIDENT & REPORTS"))
    p()
    p(f"    {cyan('incident'):<30} Investigate a service incident (runbook + RCA)")
    p(f"    {cyan('oncall-report'):<30} Generate on-call handoff report")
    p(f"    {cyan('oncall-summary'):<30} Summarize on-call alerts + generate standup")
    p(f"    {cyan('standup'):<30} Generate AI standup from git activity")
    p(f"    {cyan('sprint-report'):<30} Generate sprint summary from Jira + git + builds")
    p(f"    {cyan('sprint-velocity'):<30} Track sprint velocity across sprints from Jira")
    p(f"    {cyan('sprint-dashboard'):<30} Sprint velocity dashboard with cycle time")
    p(f"    {cyan('runbook'):<30} Execute runbooks with safety gates")
    p()

    # ── Benchmarks & Collaboration ──
    p(bold("  BENCHMARKS & COLLABORATION"))
    p()
    p(f"    {cyan('benchmark'):<30} Run agent benchmarks — quality & latency across models")
    p(f"    {cyan('bench-compare'):<30} Compare benchmark runs for quality regressions")
    p(f"    {cyan('bench-trend'):<30} Show benchmark quality trend over time")
    p(f"    {cyan('agent-pipeline'):<30} Agent pipelines — declarative agent chains")
    p(f"    {cyan('share'):<30} Start live collaboration — share session with teammates")
    p(f"    {cyan('join'):<30} Join a live collaboration session by code")
    p()

    # ── Extras ──
    p(bold("  EXTRAS"))
    p()
    p(f"    {cyan('cost'):<30} Token usage and cost dashboard")
    p(f"    {cyan('undo'):<30} Undo last agent action (file edits, git commits)")
    p(f"    {cyan('skill'):<30} Skill marketplace [list|search|install|remove|info]")
    p(f"    {cyan('snippet'):<30} Smart snippet library [search|save|list|delete|show]")
    p(f"    {cyan('velocity-predict'):<30} Sprint velocity predictor — capacity from git history")
    p(f"    {cyan('voice'):<30} Voice mode — speak to chat with agents")
    p(f"    {cyan('slack'):<30} Manage Slack integration [test|send|status|channels]")
    p(f"    {cyan('curls'):<30} Show all API curl commands")
    p(f"    {cyan('version-bump'):<30} Bump version (major/minor/patch)")
    p(f"    {cyan('api-check'):<30} Compare API endpoints with last release for breaking changes")
    p(f"    {cyan('perf-baseline'):<30} Record or compare performance baseline")
    p(f"    {cyan('prop-test'):<30} Generate Hypothesis property-based tests")
    p(f"    {cyan('test-style'):<30} Analyze project test style or generate matching tests")
    p(f"    {cyan('visual-test'):<30} Visual regression testing — capture and compare snapshots")
    p(f"    {cyan('browse'):<30} Browser agent — fetch page, extract text, scrape API docs")
    p(f"    {cyan('team-kb'):<30} Team knowledge base [list|add|get|search|delete]")
    p(f"    {cyan('onboard-tour'):<30} Generate onboarding tour for new developers")
    p()

    # ── Chat Commands ──
    p(bold("  CHAT COMMANDS (inside chat REPL)"))
    p()
    p(f"    {cyan('/help'):<30} Show chat help")
    p(f"    {cyan('/quit'):<30} Exit the chat")
    p(f"    {cyan('/agent <name>'):<30} Switch to a specialist agent")
    p(f"    {cyan('/agents'):<30} List available agents")
    p(f"    {cyan('/session'):<30} Session management")
    p(f"    {cyan('/clear'):<30} Clear conversation context")
    p(f"    {cyan('/history'):<30} Show conversation history")
    p(f"    {cyan('/resume'):<30} Resume a previous session")
    p()

    # ── Quick Start ──
    p(bold("  QUICK START"))
    p()
    p(f"    {dim('cd /path/to/your-project')}")
    p(f"    {dim('code-agents init          # configure (smart wizard)')}")
    p(f"    {dim('code-agents start         # start server')}")
    p(f"    {dim('code-agents chat          # open interactive chat')}")
    p(f"    {dim('code-agents doctor        # verify everything works')}")
    p()
    p(f"  {dim('Run')} code-agents <command> --help {dim('for detailed usage of any command.')}")
    p()


def main():
    """Delegate to cli.main — backward compat for `from code_agents.cli.cli_completions import main`."""
    from .cli import main as _cli_main

    return _cli_main()


if __name__ == "__main__":
    from .cli import main as _cli_main

    _cli_main()

