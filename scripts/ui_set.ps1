# usage: ui_set.ps1 -Title <window title substring> -Name <slider name> -Value <number>
# Sets a UI Automation RangeValue (e.g. Paint's brush "大小" slider) and prints the resulting value.
param([Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][double]$Value)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if (-not $p) { Write-Error "no window matching '$Title'"; exit 2 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$cond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Name)),
  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Slider)))
$el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if (-not $el) { Write-Error "slider '$Name' not found"; exit 3 }
$pat = $el.GetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern)
$pat.SetValue($Value)
"{0} = {1}" -f $Name, $pat.Current.Value
