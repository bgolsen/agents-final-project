# Starts all 4 specialist A2A servers plus the coordinator API, each in its
# own titled PowerShell window, using the repo's virtualenv. Window titles
# (e.g. "Agent: diagnostic (:8002)") make it easy to identify and close a
# specific agent's window on camera for the SCRIPT.md edge-case demo.
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$repoRoot = Join-Path $PSScriptRoot ".."

function Start-TitledAgent {
    param([string]$Title, [string]$ArgsLine)
    $cmd = "`$host.UI.RawUI.WindowTitle = '$Title'; & '$venvPython' $ArgsLine"
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", $cmd -WorkingDirectory $repoRoot
}

$agentPorts = @{ monitoring = 8001; diagnostic = 8002; remediation = 8003; postmortem = 8004 }
foreach ($agent in $agentPorts.Keys) {
    Start-TitledAgent -Title "Agent: $agent (:$($agentPorts[$agent]))" -ArgsLine "-m incident_response.a2a_server $agent"
}
Start-TitledAgent -Title "Coordinator API (:8110)" -ArgsLine "-m incident_response.api"

Write-Host "Started monitoring(8001), diagnostic(8002), remediation(8003), postmortem(8004) agents and coordinator API(8110), each in a titled window."
Write-Host "Run 'python -m incident_response.run_incident --no-spawn' to start a demo incident against them."
