# usage: uia_dump.ps1 [-MaxNodes 300] [-MaxDepth 8] [-Title <window title substring> | -Hwnd <exact window handle>]  (default = foreground window)  -> text outline of the foreground window
param([int]$MaxNodes = 300, [int]$MaxDepth = 8, [string]$Title = "", [long]$Hwnd = 0)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -Namespace W -Name D -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][W.D]::SetProcessDPIAware()  # physical pixels, same space as screenshot.ps1 and the mouse
Add-Type -Namespace W -Name F -MemberDefinition '[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();'
if ($Hwnd -ne 0) { $h = [IntPtr]$Hwnd }
elseif ($Title) {
  $proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
  $h = if ($proc) { $proc.MainWindowHandle } else { [IntPtr]::Zero }
} else { $h = [W.F]::GetForegroundWindow() }
if ($h -eq [IntPtr]::Zero) { exit 0 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$script:n = 0
function Walk($el, $d) {
  if ($script:n -ge $MaxNodes -or $d -gt $MaxDepth) { return }
  $c = $el.Current
  $role = $c.ControlType.ProgrammaticName -replace '^ControlType\.', ''
  $name = ($c.Name -replace '\s+', ' ').Trim()
  $interactive = $role -in 'Button','Edit','CheckBox','RadioButton','ComboBox','MenuItem','TabItem','Hyperlink','ListItem','Document'
  if ($name -or $interactive) {
    $r = $c.BoundingRectangle
    if (-not $r.IsEmpty -and -not $c.IsOffscreen) {
      $script:n++
      '{0}{1} "{2}" @({3},{4},{5}x{6}){7}' -f ('  ' * $d), $role, $name, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height, $(if (-not $c.IsEnabled) { ' disabled' } else { '' })
    }
  }
  $ch = $walker.GetFirstChild($el)
  while ($ch -ne $null) { Walk $ch ($d + 1); $ch = $walker.GetNextSibling($ch) }
}
Walk $root 0
