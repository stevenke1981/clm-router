# usage: focus.ps1 <window title substring> -> brings the first matching top-level window to the foreground
param([Parameter(Mandatory)][string]$Title)
Add-Type -Namespace W -Name U -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);'
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if (-not $p) { Write-Error "no window matching '$Title'"; exit 2 }
[void][W.U]::ShowWindow($p.MainWindowHandle, 9)
[void][W.U]::SetForegroundWindow($p.MainWindowHandle)
