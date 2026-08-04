param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [int[]]$Ports
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Freeing ports: $($Ports -join ' ')"

foreach ($port in $Ports) {
    Write-Host " - checking port $port ..."
    $killed = @()

    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen
    foreach ($conn in $listeners) {
        $procId = [int]$conn.OwningProcess
        if ($procId -gt 0 -and $killed -notcontains $procId) {
            Write-Host "    kill PID $procId"
            Stop-Process -Id $procId -Force
            $killed += $procId
        }
    }

    if ($killed.Count -eq 0) {
        # Fallback for environments where Get-NetTCPConnection is unavailable.
        $rx = "[\\.:]$port\s+\S+\s+LISTENING\s+(\d+)\s*$"
        netstat -ano | ForEach-Object {
            if ($_ -match $rx) {
                $procId = [int]$Matches[1]
                if ($procId -gt 0 -and $killed -notcontains $procId) {
                    Write-Host "    kill PID $procId via netstat"
                    Stop-Process -Id $procId -Force
                    $killed += $procId
                }
            }
        }
    }

    if ($killed.Count -eq 0) {
        Write-Host "    port ${port}: no previous LISTENING process"
        continue
    }

    $deadline = (Get-Date).AddSeconds(6)
    $released = $false
    while ((Get-Date) -lt $deadline) {
        $busy = $false
        if (Get-NetTCPConnection -LocalPort $port -State Listen) {
            $busy = $true
        }
        elseif (netstat -ano | Select-String -Pattern "[\\.:]$port\s+\S+\s+LISTENING") {
            $busy = $true
        }

        if (-not $busy) {
            Write-Host "    port ${port}: released"
            $released = $true
            break
        }
        Start-Sleep -Milliseconds 200
    }

    if (-not $released) {
        Write-Host "    WARNING: port $port may still be busy"
    }
}

Write-Host "Port cleanup done."
Write-Host ""
