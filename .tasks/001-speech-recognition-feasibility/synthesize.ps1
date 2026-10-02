param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$corpus = Join-Path "$root" 'corpus'
$manifest = Get-Content -LiteralPath (Join-Path "$corpus" 'synthetic.json') -Raw |
    ConvertFrom-Json
$synthesizer = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)

try {
    $synthesizer.SelectVoice($manifest.voice)
    foreach ($clip in $manifest.clips) {
        if ($clip.id -notmatch '^(question|filter|preference|value|silence)-[0-9]{2}$') {
            throw 'Unsupported clip identifier'
        }
        $target = Join-Path "$corpus" "$($clip.id).wav"
        if (Test-Path -LiteralPath "$target") { throw "Existing clip: $($clip.id)" }
    }
    if ($ValidateOnly) {
        Write-Output "Validated $($manifest.clips.Count) synthetic clips; no files created"
        return
    }
    foreach ($clip in $manifest.clips) {
        if ($clip.outcome -eq 'no_speech') { continue }
        $target = Join-Path "$corpus" "$($clip.id).wav"
        $synthesizer.SetOutputToWaveFile("$target", $format)
        $synthesizer.Speak($clip.text)
        $synthesizer.SetOutputToNull()
        Write-Output "Generated $($clip.id) using offline Windows synthesis"
    }
} finally {
    $synthesizer.Dispose()
}