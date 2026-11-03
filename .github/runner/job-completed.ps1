# Wipe job files so a later refused job cannot upload leftovers (ADR 0027).
# Install the live copy by hand under C:\ProgramData\piperobot-runner\ and name it
# in ACTIONS_RUNNER_HOOK_JOB_COMPLETED in the runner's .env.
try {
    if ([string]::IsNullOrWhiteSpace($env:GITHUB_WORKSPACE) -or
        [string]::IsNullOrWhiteSpace($env:RUNNER_WORKSPACE)) {
        throw 'GITHUB_WORKSPACE and RUNNER_WORKSPACE must both be set.'
    }
    $workspace = [IO.Path]::GetFullPath($env:GITHUB_WORKSPACE)
    $runnerWorkspace = [IO.Path]::GetFullPath($env:RUNNER_WORKSPACE)
    if (-not (Test-Path -LiteralPath $workspace -PathType Container) -or
        -not (Test-Path -LiteralPath $runnerWorkspace -PathType Container)) {
        throw 'GITHUB_WORKSPACE and RUNNER_WORKSPACE must both exist as directories.'
    }
    $workspaceInfo = [IO.DirectoryInfo]::new($workspace)
    $runnerInfo = [IO.DirectoryInfo]::new($runnerWorkspace)
    if ($null -eq $workspaceInfo.Parent -or
        $workspaceInfo.Parent.FullName -ine $runnerInfo.FullName) {
        throw 'GITHUB_WORKSPACE must be a direct child of RUNNER_WORKSPACE.'
    }
    if ($null -eq $runnerInfo.Parent -or $runnerInfo.Parent.Name -ine '_work') {
        throw "RUNNER_WORKSPACE's parent must be named _work."
    }
    if (@('_tool', '_temp', '_actions', '_work', '_PipelineMapping', '_update') -icontains $workspaceInfo.Name) {
        throw 'GITHUB_WORKSPACE names a protected runner folder.'
    }
    $entries = @(Get-ChildItem -LiteralPath $workspace -Force -ErrorAction Stop)
} catch {
    Write-Output "Refused workspace wipe: $($_.Exception.Message)"
    exit 1
}

function Remove-WorkspaceEntry {
    param([IO.FileSystemInfo]$Entry)

    try {
        if ($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            if ($Entry.Attributes -band [IO.FileAttributes]::Directory) {
                [IO.Directory]::Delete($Entry.FullName, $false)
            } else {
                [IO.File]::Delete($Entry.FullName)
            }
        } elseif ($Entry.Attributes -band [IO.FileAttributes]::Directory) {
            foreach ($child in Get-ChildItem -LiteralPath $Entry.FullName -Force -ErrorAction Stop) {
                Remove-WorkspaceEntry -Entry $child
            }
            [IO.Directory]::Delete($Entry.FullName, $false)
        } else {
            $protectedAttributes = [IO.FileAttributes]::ReadOnly -bor
                [IO.FileAttributes]::Hidden -bor [IO.FileAttributes]::System
            if ($Entry.Attributes -band $protectedAttributes) {
                $Entry.Attributes = $Entry.Attributes -band (-bnot $protectedAttributes)
            }
            [IO.File]::Delete($Entry.FullName)
        }
    } catch {
        Write-Output "Failed to wipe '$($Entry.FullName)': $($_.Exception.Message)"
        exit 1
    }
}

foreach ($entry in $entries) {
    Remove-WorkspaceEntry -Entry $entry
}
Write-Output "Wiped job workspace: $workspace ($($entries.Count) entries)."
exit 0
