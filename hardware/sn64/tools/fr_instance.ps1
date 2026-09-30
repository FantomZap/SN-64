# Drive one extra Freerouting API-server instance (its own JVM, so its own CPU core) for a
# routing variant of the main board. Freerouting time-slices jobs inside one instance, so
# parallel variants need parallel instances.
#
#   fr_instance.ps1 -Port 37870 -Name lowvia -Settings '{"viaCosts":20,...}'      # start + submit
#   fr_instance.ps1 -Port 37870 -Status                                          # poll
#   fr_instance.ps1 -Port 37870 -Download build\route-pcb\variant-lowvia.ses     # fetch the .ses
#   fr_instance.ps1 -Port 37870 -Stop                                            # kill the JVM
# State (job id, pid) is kept in build\route-pcb\fr-<port>.json.
param(
    [int]$Port = 37870,
    [string]$Name = 'variant',
    [string]$Settings = '{}',
    [string]$SettingsFile = '',          # JSON file; safer than quoting JSON on a command line
    [string]$Dsn = 'build\route-pcb\sn64.dsn',
    [switch]$Status,
    [string]$Download = '',
    [switch]$Stop
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location $repo
$jar = 'C:\Users\RyanB\Tools\freerouting\freerouting-2.4.1.jar'
$state = "build\route-pcb\fr-$Port.json"
$base = "http://127.0.0.1:$Port/v1"
$hdr = @{ 'Freerouting-Profile-ID' = 'f980f25e-1d3e-4c34-802b-fa5c5b36567d'; 'Freerouting-Environment-Host' = 'sn64-variant/1.0'; 'Accept' = 'application/json' }

function Call($method, $path, $body) {
    $args = @{ Uri = "$base$path"; Method = $method; Headers = $hdr; UseBasicParsing = $true; TimeoutSec = 120 }
    if ($null -ne $body) { $args.Body = $body; $args.ContentType = 'application/json' }
    return (Invoke-WebRequest @args).Content | ConvertFrom-Json
}

if ($Stop) {
    if (Test-Path $state) { $s = Get-Content $state | ConvertFrom-Json; Stop-Process -Id $s.pid -Force -ErrorAction SilentlyContinue; Remove-Item $state }
    "stopped instance on port $Port"; return
}
if ($Status) {
    $s = Get-Content $state | ConvertFrom-Json
    $j = Call 'GET' "/jobs/$($s.job)" $null
    $o = $j.output.statistics
    "port $Port $($s.name): state=$($j.state) stage=$($j.stage) pass=$($j.current_pass) cpu=$([int]$j.resource_usage.cpu_time)s nets=$($o.nets.total_count) traces=$($o.traces.total_count) vias=$($o.vias.total_count)"
    return
}
if ($Download) {
    $s = Get-Content $state | ConvertFrom-Json
    $o = Call 'GET' "/jobs/$($s.job)/output" $null
    [IO.File]::WriteAllBytes((Join-Path $repo $Download), [Convert]::FromBase64String($o.data))
    "saved $Download ($((Get-Item $Download).Length) bytes) from job $($s.job)"; return
}

# ---- start the instance and submit the job
if ($SettingsFile) { $Settings = Get-Content (Join-Path $repo $SettingsFile) -Raw }
$null = $Settings | ConvertFrom-Json     # fail before starting a JVM if the JSON is bad
if (Test-Path $state) { throw "$state exists: an instance may already run on port $Port (use -Stop first)" }
$p = Start-Process -FilePath 'java' -PassThru -WindowStyle Hidden -ArgumentList @('-jar', $jar, '--gui.enabled=false', '--api_server.enabled=true',
    "--api_server-endpoints=http://127.0.0.1:$Port", '--api_server.authentication.enabled=false', '-da') `
    -RedirectStandardOutput "build\route-pcb\fr-$Port.log" -RedirectStandardError "build\route-pcb\fr-$Port.err"
try {
    $up = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        try { $null = Invoke-WebRequest -Uri "$base/system/status" -UseBasicParsing -TimeoutSec 5; $up = $true; break } catch {}
    }
    if (-not $up) { throw "instance on port $Port did not come up" }
    $sess = Call 'POST' '/sessions/create' '{}'
    $job = Call 'POST' '/jobs/enqueue' (@{ session_id = $sess.id; name = "sn64-$Name"; priority = 'NORMAL' } | ConvertTo-Json)
    $dsnBytes = [IO.File]::ReadAllBytes((Join-Path $repo $Dsn))
    $null = Call 'POST' "/jobs/$($job.id)/input" (@{ filename = "sn64-$Name.dsn"; data = [Convert]::ToBase64String($dsnBytes) } | ConvertTo-Json)
    $null = Call 'POST' "/jobs/$($job.id)/settings" $Settings
    $null = Call 'PUT' "/jobs/$($job.id)/start" $null
} catch {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    throw
}
@{ port = $Port; pid = $p.Id; session = $sess.id; job = $job.id; name = $Name } | ConvertTo-Json | Set-Content $state
"started $Name on port ${Port}: pid $($p.Id), job $($job.id)"
