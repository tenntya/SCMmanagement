Param()
$root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$credFile = Join-Path $root 'GIT_CREDENTIALS.txt'
if (-not (Test-Path $credFile)) { Write-Error "GIT_CREDENTIALS.txt not found"; exit 1 }
$lines = Get-Content $credFile -Encoding UTF8
$map = @{}
foreach ($l in $lines) {
  if (-not $l) { continue }
  if ($l.Trim().StartsWith('#')) { continue }
  if ($l -notmatch '=') { continue }
  $kv = $l.Split('=',2)
  $map[$kv[0].Trim()] = $kv[1].Trim()
}
$user = $map['GIT_USERNAME']
$token = $map['GIT_TOKEN']
$repo = $map['GIT_REPO']
if (-not $user -or -not $token -or -not $repo) { Write-Error "Please fill GIT_USERNAME/GIT_TOKEN/GIT_REPO in GIT_CREDENTIALS.txt"; exit 1 }
git remote -v | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "git not available"; exit 1 }
$origUrl = (git remote get-url origin).Trim()
try {
  $u = [System.Uri]$repo
  $netloc = "$($u.UserInfo)" # may be empty
  $withToken = "{0}://{1}:{2}@{3}{4}" -f $u.Scheme, $user, $token, $u.Host, $u.AbsolutePath
  git remote set-url origin $withToken | Out-Null
  git push -u origin HEAD
}
finally {
  if ($origUrl) { git remote set-url origin $origUrl | Out-Null }
}

