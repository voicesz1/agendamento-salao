$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$gradleVersion = "8.11.1"
$cacheDir = Join-Path $projectRoot ".build-cache"
$gradleHome = Join-Path $cacheDir "gradle-$gradleVersion"
$gradleZip = Join-Path $cacheDir "gradle-$gradleVersion-bin.zip"
$gradleExecutable = Join-Path $gradleHome "gradle-$gradleVersion\bin\gradle.bat"

$localProperties = Join-Path $projectRoot "local.properties"
if (-not (Test-Path -LiteralPath $localProperties)) {
    $sdkPath = $env:ANDROID_SDK_ROOT
    if (-not $sdkPath) { $sdkPath = $env:ANDROID_HOME }
    if (-not $sdkPath -and $env:LOCALAPPDATA) {
        $defaultSdkPath = Join-Path $env:LOCALAPPDATA "Android\Sdk"
        if (Test-Path -LiteralPath $defaultSdkPath) { $sdkPath = $defaultSdkPath }
    }
    if (-not $sdkPath -or -not (Test-Path -LiteralPath $sdkPath)) {
        throw "Instale o Android Studio e o Android SDK 36. Depois abra este projeto uma vez para o Android Studio criar android/local.properties."
    }
    $sdkPath = $sdkPath.Replace("\", "\\")
    Set-Content -LiteralPath $localProperties -Value "sdk.dir=$sdkPath" -Encoding Ascii
}

if (-not (Test-Path -LiteralPath $gradleExecutable)) {
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
    if (-not (Test-Path -LiteralPath $gradleZip)) {
        Invoke-WebRequest `
            -Uri "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip" `
            -OutFile $gradleZip
    }
    Expand-Archive -LiteralPath $gradleZip -DestinationPath $gradleHome -Force
}

Push-Location $projectRoot
try {
    & $gradleExecutable --no-daemon bundleRelease
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Bundle compilado em app\build\outputs\bundle\release\app-release.aab"
} finally {
    Pop-Location
}
