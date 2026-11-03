# Runner job-started hook: install the live copy by hand outside the repo on the runner machine
# (ADR 0027, docs/knowledge/ci.md). Adding a self-hosted workflow requires updating this allowlist
# and redeploying the live copy before the new workflow can run.
$AllowedWorkflows = @('gpu-smoke.yml', 'isaac-render.yml')

if ($env:GITHUB_REPOSITORY -cne 'Andresdurango85/PipeRobot') {
    Write-Output 'Refused job: repository is missing or is not Andresdurango85/PipeRobot.'
    exit 1
}
if (@('push', 'workflow_dispatch', 'schedule') -cnotcontains $env:GITHUB_EVENT_NAME) {
    Write-Output 'Refused job: event is missing or is not push, workflow_dispatch, or schedule.'
    exit 1
}
if ($env:GITHUB_WORKFLOW_REF -cnotmatch '\AAndresdurango85/PipeRobot/\.github/workflows/([^/@]+)@refs/heads/[^\s]+\z') {
    Write-Output 'Refused job: workflow ref is missing or is not a repository branch workflow ref.'
    exit 1
}
if ($AllowedWorkflows -cnotcontains $Matches[1]) {
    Write-Output "Refused job: workflow '$($Matches[1])' is not in the allowlist."
    exit 1
}
Write-Output "Allowed job: $env:GITHUB_WORKFLOW_REF (event: $env:GITHUB_EVENT_NAME)."
exit 0
