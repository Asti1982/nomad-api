param(
    [string]$EnvFile = "",
    [string]$ServiceId = "srv-cs8d1ldumphs7384hn2g"
)

if ($EnvFile -and (Test-Path $EnvFile)) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*RENDER_API_KEY\s*=\s*(.+)\s*$') {
            $env:RENDER_API_KEY = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
}

if (-not $env:RENDER_API_KEY) {
    Write-Error "Set RENDER_API_KEY or pass -EnvFile <path-to-private-env>."
    exit 1
}

$headers = @{ Authorization = "Bearer $env:RENDER_API_KEY" }
$service = Invoke-RestMethod -Headers $headers -Uri "https://api.render.com/v1/services/$ServiceId"
$deploys = Invoke-RestMethod -Headers $headers -Uri "https://api.render.com/v1/services/$ServiceId/deploys?limit=1"

[pscustomobject]@{
    service = $service.name
    id = $service.id
    repo = $service.repo
    branch = $service.branch
    autoDeploy = $service.autoDeploy
    autoDeployTrigger = $service.autoDeployTrigger
    liveStatus = $deploys.deploy.status
    liveCommit = $deploys.deploy.commit.id
    liveMessage = $deploys.deploy.commit.message
    liveDeployId = $deploys.deploy.id
} | ConvertTo-Json -Depth 4
