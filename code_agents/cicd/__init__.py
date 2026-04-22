"""CI/CD subpackage — Jenkins, ArgoCD, Git, Testing, Pipeline clients."""

from .jenkins_client import JenkinsClient, JenkinsError  # noqa: F401
from .argocd_client import ArgoCDClient, ArgoCDError, resolve_app_name  # noqa: F401
from .k8s_client import K8sClient, K8sError  # noqa: F401
from .git_client import GitClient, GitOpsError, _validate_ref  # noqa: F401
from .testing_client import TestingClient, TestingError  # noqa: F401
from .kibana_client import KibanaClient, KibanaError  # noqa: F401
from .jira_client import JiraClient, JiraError  # noqa: F401
from .sanity_checker import (  # noqa: F401
    SanityRule, CheckResult, load_rules, run_check, run_all_checks,
    format_report, DEFAULT_RULES,
)
from .pipeline_state import (  # noqa: F401
    PipelineStateManager, PipelineRun, StepStatus, STEP_NAMES,
    pipeline_manager,
)
from .endpoint_scanner import (  # noqa: F401
    scan_all, scan_rest_endpoints, scan_grpc_services, scan_kafka_listeners,
    generate_curls, generate_grpc_cmds, generate_kafka_cmds,
    load_cache, save_cache, background_scan,
    RestEndpoint, GrpcService, KafkaListener, ScanResult,
)
from .review_config import (  # noqa: F401
    ReviewConfig, load_review_config, should_skip_file,
    is_auto_approve, format_config_for_prompt,
)
from .jacoco_parser import (  # noqa: F401
    ClassCoverage, CoverageReport,
    parse_jacoco_xml, find_jacoco_xml, get_uncovered_methods,
    format_coverage_report, coverage_meets_threshold,
)
