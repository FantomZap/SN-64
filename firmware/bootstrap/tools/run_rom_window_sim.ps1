# SN64 bootstrap <-> FPGA endpoint integration simulation.
# Builds firmware/bootstrap/tests/tb_bootstrap_rom_window.sv against the
# N64 endpoint sources (same list fpga/tools/evaluate.py uses for
# tb_n64_endpoint), runs it on the converted image, then runs it again with
# +corrupt_load, which must fail. Run from the repository root after
# `make -C firmware/bootstrap words` (needs build/generated/summercart64/n64_cic.sv
# from fpga/tools/build_cic.py).
param(
    [string]$Image = 'build/n64-bootstrap/sn64_bootstrap_words.mem',
    [int]$RomAddrBits = 17,
    [string]$Mdir = 'build/n64-bootstrap/verilator'
)
$ErrorActionPreference = 'Stop'
. "$env:USERPROFILE\.codex\tools\oss-cad-suite-20260928\oss-cad-suite\environment.ps1"
$env:PATH = "$env:USERPROFILE\.codex\tools\w64devkit-2.10.0\w64devkit\bin;" + $env:PATH
$env:VERILATOR_ROOT = "$env:USERPROFILE\.codex\tools\oss-cad-suite-20260928\oss-cad-suite\share\verilator"

$serv = Get-ChildItem fpga/vendor/summercart64/fw/rtl/serv/*.v | ForEach-Object { 'fpga/vendor/summercart64/fw/rtl/serv/' + $_.Name }
$src = @('fpga/vendor/summercart64/fw/rtl/memory/mem_bus.sv', 'fpga/rtl/sn64_n64_reg_bus.sv',
         'fpga/vendor/summercart64/fw/rtl/n64/n64_scb.sv', 'fpga/vendor/summercart64/fw/rtl/n64/n64_pi_fifo.sv',
         'fpga/vendor/summercart64/fw/rtl/n64/n64_pi.sv', 'build/generated/summercart64/n64_cic.sv',
         'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_frame_window.sv',
         'fpga/rtl/sn64_n64_endpoint.sv') + $serv + @('firmware/bootstrap/tests/tb_bootstrap_rom_window.sv')

verilator_bin --binary --timing --build-jobs 4 -Wno-fatal --top-module tb_bootstrap_rom_window "-GAW=$RomAddrBits" --Mdir $Mdir @src | Out-Null
if ($LASTEXITCODE -ne 0) { throw "verilator build failed" }
$exe = Join-Path $Mdir 'Vtb_bootstrap_rom_window.exe'

& $exe "+image=$Image" | Select-String -Pattern '^(PASS|FAIL|  FAIL)'
if ($LASTEXITCODE -ne 0) { throw "integration bench failed" }

$neg = & $exe "+image=$Image" '+corrupt_load' 2>&1 | Select-String -Pattern '^(PASS|FAIL|  FAIL)'
$neg
if ($LASTEXITCODE -eq 0) { throw "fault injection NOT detected" }
Write-Output 'NEGATIVE: +corrupt_load run failed as required'
