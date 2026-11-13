<#
.SYNOPSIS
Registra una captura identificada por el operador durante la prueba fisica.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateRange(1,2147483647)][int]$Inspeccion,
    [Parameter(Mandatory)][ValidateSet('ok','falta_embutido_material','ruptura_deformacion')][string]$Real,
    [Parameter(Mandatory)][string]$Sesion,
    [Parameter(Mandatory)][string]$Luz,
    [Parameter(Mandatory)][int]$Angulo,
    [Parameter(Mandatory)][ValidateRange(1,1000)][int]$DistanciaCm,
    [string]$Servidor = 'http://127.0.0.1:8000',
    [string]$Destino = (Join-Path $PSScriptRoot '../outputs/webcam-estampado/ensayos.csv')
)
$ErrorActionPreference = 'Stop'
$history = Invoke-RestMethod "$Servidor/history?limit=500"
$row = $history.inspections | Where-Object { $_.id -eq $Inspeccion }
if (-not $row.classification) { throw 'Selecciona una clasificacion entre las ultimas 500 inspecciones.' }
$destinationPath = [IO.Path]::GetFullPath($Destino)
if ((Test-Path -LiteralPath $destinationPath) -and
    (Import-Csv -LiteralPath $destinationPath | Where-Object { $_.servidor -eq $Servidor -and $_.id -eq $Inspeccion })) {
    throw 'Esta captura ya figura en el registro de webcam.'
}
$value = $row.classification
$null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destinationPath))
[pscustomobject]@{
    sesion=$Sesion; id=$Inspeccion; utc=$row.timestamp; servidor=$Servidor
    real=$Real; luz=$Luz; angulo=$Angulo; distancia_cm=$DistanciaCm
    prediccion=$value.predicted; estado=$row.status; umbral=$value.review_threshold
    ok=$value.scores.ok; falta_embutido_material=$value.scores.falta_embutido_material
    ruptura_deformacion=$value.scores.ruptura_deformacion; gpu=$value.device; inferencia_ms=$value.inference_ms
    defectuosa_como_ok=($Real -ne 'ok' -and $value.predicted -eq 'ok')
    pesos_sha256=$value.weights_sha256; imagen=$value.captures.original_url
} | Export-Csv -LiteralPath $destinationPath -Encoding utf8 -NoTypeInformation -Append
Write-Output $destinationPath
