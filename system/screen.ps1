Set-ItemProperty `
  -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" `
  -Name "CABCOption" `
  -Type DWord `
  -Value 0