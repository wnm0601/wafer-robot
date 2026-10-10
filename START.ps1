param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src\wafer_cart_keyboard_drive'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$required = @('scripts/manual_first_drive.py','src/wafer_cart_keyboard_drive/wafer_cart_keyboard_drive/manual_hardware.py','config/manual_simulation.json','src/wafer_cart_mapping/config/booth_mock.json','src/wafer_cart_mapping/config/reference_measurements.json','firmware/mega_cart/platformio.ini','requirements-manual.txt')
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $file) -PathType Leaf)) { throw "필수 파일 누락: $file" }
}
if ($CheckOnly) { Write-Output 'PACKAGE_LAYOUT_PASS / NO_SERIAL / NO_INSTALL'; exit 0 }
function Invoke-PythonChecked {
    param([string[]]$Arguments)
    if (-not (Test-Path -LiteralPath $python)) { throw '먼저 메뉴 1에서 실행 환경을 설치해 주세요.' }
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "실행 실패: 종료 코드 $LASTEXITCODE. 오류를 확인하고 모터 전원을 OFF로 유지해 주세요." }
}
function Read-Port {
    $port = (Read-Host '메뉴 2에서 확인한 Arduino COM 번호를 입력하세요 (예: COM7)').Trim().ToUpperInvariant()
    if ($port -notmatch '^COM[1-9][0-9]*$') { throw '올바른 COM 번호가 아닙니다.' }
    return $port
}
Write-Host '웨이퍼 대차 수동 검사 전달본 / 2026-10-10'
Write-Host '자동 업로드·자동 주행 없음. 이 창은 메뉴만 표시합니다.'
Write-Host '실차 카메라 안전·전원 감시 미연결, 4륜 실차 매핑 잠금. 모터 위치 표시는 추정입니다.'
Write-Host '1: Python 가상환경 + pyserial 설치 (인터넷 필요, 장치 접근 없음)'
Write-Host '2: COM 포트 목록 (포트 개방 없음)'
Write-Host '3: PC 전용 모의시험 + 단위시험 (장치 접근 없음)'
Write-Host '4: 모터 전원 OFF 정지 진단 (실제 COM 접속, 회전 명령 없음)'
Write-Host '5: 실제 수동 터미널 (명시적 확인 후 키를 누르면 출력 가능)'
Write-Host '6: 실제 수동 GUI (명시적 확인 후 조작하면 출력 가능)'
Write-Host '7: C++ 기반 모의 GUI (Ubuntu-24.04 WSL + g++ 필요)'
Write-Host '0: 종료'
$choice = Read-Host '번호'
switch ($choice) {
    '0' { exit 0 }
    '1' {
        & py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 (64bit, Tcl/Tk 포함)을 먼저 설치해 주세요.' }
        Invoke-PythonChecked -Arguments @('-m','pip','install','-r','requirements-manual.txt')
        Invoke-PythonChecked -Arguments @('-c','import serial, tkinter; print("DEPENDENCIES_OK")')
    }
    '2' { Invoke-PythonChecked -Arguments @('-m','serial.tools.list_ports','-v') }
    '3' {
        Invoke-PythonChecked -Arguments @('scripts/manual_first_drive.py','--smoke')
        Invoke-PythonChecked -Arguments @('-m','unittest','discover','-s','src/wafer_cart_keyboard_drive/test')
    }
    '4' {
        if ((Read-Host '배터리 분리·USB만·다른 조작 앱/시리얼 모니터 종료를 확인했다면 OFF 입력') -cne 'OFF') { throw '취소했습니다. 포트를 열지 않았습니다.' }
        $port = Read-Port
        Invoke-PythonChecked -Arguments @('scripts/manual_first_drive.py','--real','--port',$port,'--no-power-feedback','--inspect-real','--diagnostics')
    }
    { $_ -in @('5','6') } {
        Write-Host '받침대·바퀴 주변 확보·즉시 전원 차단 담당자·배선 점검 후에만 진행하세요.'
        if ((Read-Host '실제 출력 가능한 수동 시험임을 확인했다면 MANUAL 입력') -cne 'MANUAL') { throw '취소했습니다. 포트를 열지 않았습니다.' }
        $port = Read-Port
        $arguments = @('scripts/manual_first_drive.py','--real','--port',$port,'--no-power-feedback')
        if ($choice -eq '5') { $arguments += @('--terminal','--percent','1','--diagnostics') }
        Write-Host '기존 프로그램에서 CONNECT COM번호를 다시 입력해야 연결됩니다. 시작값 1%는 회전 보장값이 아닙니다.'
        Invoke-PythonChecked -Arguments $arguments
    }
    '7' {
        if ((Read-Host '이 옵션은 가상 구동입니다. WSL 준비가 됐다면 SIM 입력') -cne 'SIM') { exit 0 }
        Invoke-PythonChecked -Arguments @('scripts/manual_first_drive.py')
    }
    default { throw '지원하지 않는 메뉴입니다. 장치에 접근하지 않았습니다.' }
}
