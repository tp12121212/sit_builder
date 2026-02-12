[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$UserPrincipalName,

    [Parameter(Mandatory = $false)]
    [string]$Organization,
    
    [Parameter(Mandatory = $false)]
    [string]$WinFile,
    
    [Parameter(Mandatory = $false)]
    [string]$MacFile,
    
    [Parameter(Mandatory = $false)]
    [string]$PythonScriptPath = "./keyword_extraction.py",
    
    [Parameter(Mandatory = $false)]
    [string]$PythonExecutable = "python3",  # NEW: Allow custom Python path

    [Parameter(Mandatory = $false)]
    [switch]$PreserveCase
)

$accessToken = $env:EXO_ACCESS_TOKEN
if ($accessToken) {
    $connectParams = @{
        AccessToken = $accessToken
        ShowBanner = $false
        ErrorAction = 'Stop'
    }
    if ($Organization) {
        $connectParams.Organization = $Organization
    }
    if ($UserPrincipalName) {
        $connectParams.UserPrincipalName = $UserPrincipalName
    }
    Connect-ExchangeOnline @connectParams
}
else {
    if (-not $UserPrincipalName) {
        throw "UserPrincipalName is required when EXO_ACCESS_TOKEN is not provided"
    }
    Connect-ExchangeOnline -UserPrincipalName $UserPrincipalName -ShowBanner:$false -ErrorAction Stop
}

try {
    # Determine file path based on OS
    if ($IsWindows) {
        $FilePath = if ($WinFile) { $WinFile } else { $MacFile }
    }
    elseif ($IsMacOS) {
        $FilePath = if ($MacFile) { $MacFile } else { $WinFile }
    }
    else {
        throw "Unsupported OS"
    }

    if (-not (Test-Path -LiteralPath $FilePath)) {
        throw "File not found: $FilePath"
    }

    # Extract text
    $fileBytes = [System.IO.File]::ReadAllBytes($FilePath)
    $extractionResult = Test-TextExtraction -FileData $fileBytes

    # Create array of extracted texts with metadata
    $extractedStreams = @()
    foreach ($result in $extractionResult.ExtractedResults) {
        $extractedStreams += @{
            StreamName = $result.StreamName
            StreamId = $result.StreamId
            StreamTextLength = $result.StreamTextLength
            ExtractedStreamText = $result.ExtractedStreamText
        }
    }

    # Convert to JSON and pass to Python
    $jsonInput = $extractedStreams | ConvertTo-Json -Depth 10 -Compress

    # Call Python script with JSON input using specified Python executable.
    # Emit only machine-readable output for backend parsing.
    $pythonArgs = @($PythonScriptPath)
    if ($PreserveCase) {
        $pythonArgs += "--preserve-case"
    }
    $pythonOutput = $jsonInput | & $PythonExecutable @pythonArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "keyword_extraction.py failed: $pythonOutput"
    }

    Write-Output $pythonOutput

}
catch {
    Write-Error $_
    exit 1
}
finally {
    Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
}
