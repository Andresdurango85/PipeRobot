# Runner job-started hook: install the live copy by hand outside the repo on the runner machine
# (ADR 0027, docs/knowledge/ci.md). Adding a self-hosted workflow requires updating this allowlist
# and redeploying the live copy before the new workflow can run.
# Failed hooks still allow always() steps; end only this job's worker on refusal
# (ADR 0027 and its follow-up).
$AllowedWorkflows = @('gpu-smoke.yml', 'isaac-render.yml')

function Stop-RefusedJob {
    try {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $PID" -ErrorAction Stop
        $parentId = $current.ParentProcessId
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $parentId" -ErrorAction Stop
        if ($parent.Name -ieq 'Runner.Worker.exe') {
            Write-Output "Ending the job's runner worker (pid $parentId) so no step runs."
            Stop-Process -Id $parentId -Force -ErrorAction Stop
        }
    } catch {
        # CIM may be unavailable, or the parent may already have exited.
    }
    exit 1
}

if ($env:GITHUB_REPOSITORY -cne 'Andresdurango85/PipeRobot') {
    Write-Output 'Refused job: repository is missing or is not Andresdurango85/PipeRobot.'
    Stop-RefusedJob
}
if (@('push', 'workflow_dispatch', 'schedule') -cnotcontains $env:GITHUB_EVENT_NAME) {
    Write-Output 'Refused job: event is missing or is not push, workflow_dispatch, or schedule.'
    Stop-RefusedJob
}
if ($env:GITHUB_WORKFLOW_REF -cnotmatch '\AAndresdurango85/PipeRobot/\.github/workflows/([^/@]+)@refs/heads/[^\s]+\z') {
    Write-Output 'Refused job: workflow ref is missing or is not a repository branch workflow ref.'
    Stop-RefusedJob
}
if ($AllowedWorkflows -cnotcontains $Matches[1]) {
    Write-Output "Refused job: workflow '$($Matches[1])' is not in the allowlist."
    Stop-RefusedJob
}
Write-Output "Allowed job: $env:GITHUB_WORKFLOW_REF (event: $env:GITHUB_EVENT_NAME)."
exit 0
