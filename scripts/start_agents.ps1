# Starts all 4 specialist A2A servers plus the coordinator API, each in its
# own PowerShell window/job, using the repo's virtualenv.
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

$agents = @("monitoring", "diagnostic", "remediation", "postmortem")
foreach ($agent in $agents) {
    Start-Process -FilePath $venvPython -ArgumentList "-m", "incident_response.a2a_server", $agent -WorkingDirectory (Join-Path $PSScriptRoot "..")
}
Start-Process -FilePath $venvPython -ArgumentList "-m", "incident_response.api" -WorkingDirectory (Join-Path $PSScriptRoot "..")

Write-Host "Started monitoring(8001), diagnostic(8002), remediation(8003), postmortem(8004) agents and coordinator API(8000)."
Write-Host "Run 'python -m incident_response.run_incident' to start a demo incident."
