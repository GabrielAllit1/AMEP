param(
    [Parameter(Mandatory = $true)]
    [string]$Repository,

    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$SourceDir = "docs/wiki"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sourcePath = (Resolve-Path $SourceDir).Path
$runnerTemp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [System.IO.Path]::GetTempPath() }
$wikiPath = Join-Path $runnerTemp ("amep-wiki-" + [guid]::NewGuid().ToString("N"))
$wikiUrl = "https://github.com/$Repository.wiki.git"

# Authenticate Git without embedding the token in the clone URL or persisting it
# in .git/config on the self-hosted runner.
$credential = "x-access-token:$Token"
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($credential))
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "http.extraheader"
$env:GIT_CONFIG_VALUE_0 = "AUTHORIZATION: basic $basic"

try {
    Write-Host "Cloning initialized GitHub Wiki repository..."
    & git clone --quiet $wikiUrl $wikiPath
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to clone $Repository.wiki.git. Confirm that the Wiki has been initialized and that GITHUB_TOKEN has contents:write permission."
    }

    # The repository docs are canonical. Rebuild the reader-facing wiki from
    # docs/wiki so stale pages cannot silently survive a publication.
    Get-ChildItem -LiteralPath $wikiPath -Force |
        Where-Object { $_.Name -ne ".git" } |
        Remove-Item -Recurse -Force

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)

    Get-ChildItem -LiteralPath $sourcePath -File -Filter "*.md" | ForEach-Object {
        $destinationName = if ($_.Name -eq "README.md") { "Home.md" } else { $_.Name }
        $destinationPath = Join-Path $wikiPath $destinationName
        $content = [System.IO.File]::ReadAllText($_.FullName)

        # GitHub Wiki uses Home.md rather than README.md for the landing page.
        # Keep canonical repository links valid after publication.
        $content = $content.Replace("(README.md", "(Home.md")
        $content = $content.Replace("../../CITATION.cff", "https://github.com/$Repository/blob/main/CITATION.cff")

        [System.IO.File]::WriteAllText($destinationPath, $content, $utf8NoBom)
    }

    & git -C $wikiPath config user.name "github-actions[bot]"
    & git -C $wikiPath config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    & git -C $wikiPath add --all

    $changes = & git -C $wikiPath status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect Wiki working tree."
    }

    if (-not $changes) {
        Write-Host "GitHub Wiki already matches docs/wiki; nothing to publish."
        exit 0
    }

    & git -C $wikiPath commit -m "Sync AMEP engineering wiki from docs/wiki"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to commit generated Wiki content."
    }

    & git -C $wikiPath push --quiet origin HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to push generated Wiki content."
    }

    Write-Host "AMEP engineering Wiki published successfully."
}
finally {
    Remove-Item Env:GIT_CONFIG_COUNT -ErrorAction SilentlyContinue
    Remove-Item Env:GIT_CONFIG_KEY_0 -ErrorAction SilentlyContinue
    Remove-Item Env:GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue

    if (Test-Path -LiteralPath $wikiPath) {
        Remove-Item -LiteralPath $wikiPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}
