# Power-control state machine: implementation and evidence

Implemented 2026-09-29. This is the digital half of the cartridge power and bus permission logic described in the [power architecture](power-architecture.md) ("Sequence and closure") and the [bridge contract](physical-cartridge-bridge.md). It passes a simulation of bring-up, shutdown and fault cases. **It has not run on hardware**, and it does not replace the analog hardware veto (eFuse, window monitor), which must still act without the FPGA.

## Plain-language summary

This block decides when the SNES cartridge gets power and when the FPGA may drive its pins. It powers things up in a fixed order: hold the cartridge in reset, turn on its 5 V, check it, turn on the 3.3 V interface rail, check it, wait, then release reset. Only then may the cartridge bridge drive the bus. If anything goes wrong it shuts off immediately, remembers what went wrong, and refuses to restart until someone deliberately clears the fault with the "run" request off. A console reset or a menu "power down" also shuts it off cleanly.

## File

[fpga/rtl/sn64_power_sequencer.sv](../../fpga/rtl/sn64_power_sequencer.sv), tested by [fpga/tests/tb_power_sequencer.sv](../../fpga/tests/tb_power_sequencer.sv) in `evaluate.py --mode sim`.

## Behaviour

`bus_permit` (to the [cartridge bridge](cartridge-bridge-implementation.md)) is a combinational AND of: state RUN, FPGA configured, host/USB system rails valid, FPGA rails valid, eFuse not faulted, no over-temperature, cartridge 5 V in window, interface rail valid, `run_request` from the [N64 mailbox](n64-endpoint-implementation.md), host not in reset, and no latched fault. It is never stored high, so losing any condition removes permission on that clock.

| State | Outputs | Leaves when |
|---|---|---|
| OFF | 5 V off, interface rail off, reset pulled | run requested, base conditions valid, host out of reset, no latched fault |
| RESET (1) | 5 V enabled (eFuse slew), reset pulled | 5 V window valid; timeout → FAULT code `0x08` |
| RAMP5 (2) | interface rail enabled | rail valid; timeout → FAULT code `0x10` |
| IFACE (3) | reset still pulled for `RESET_HOLD_MS` | hold time elapsed → reset released |
| RUN (4) | everything on, `bus_permit` may be high; `hold_reset` pulls cartridge /RESET only | request dropped or host reset → SHUTDOWN |
| SHUTDOWN (5) | reset pulled; after a run the rails stay on for `SHUTDOWN_HOLD_MS` (1 ms), then go | hold time elapsed, or at once if the 5 V was not on → OFF |
| FAULT (6) | everything off, reset pulled, fault latched | `fault_clear` while `run_request` is low → OFF |
| CART CHECK (7) | 5 V off, test current on, reset released | two rail readings in a row at or above the threshold → CHECK END; timeout → FAULT code `0x01` (enforce) or CHECK END (report only, check only) |
| CHECK END (8) | 5 V off, test current off, reset pulled | the monitor has given the rail-sense pin back → RESET, or CHECK HOLD in check-only mode |
| CHECK HOLD (9) | everything off, reset pulled | request dropped → SHUTDOWN |

The interface rail is never enabled without cartridge 5 V (translator A side must be powered first; see the power-architecture translator section). `fault_code` records the trip cause: bit 1 configuration loss, 2 host/USB rail, 3 FPGA rails… as coded in the module; bit 3 5 V window, bit 4 interface rail, bit 6 eFuse, bit 7 over-temperature. It is intended for the telemetry registers.

**Soft reset never power-cycles the cartridge.** `hold_reset` (the N64 menu's "reset SNES" action) behaves like the console's reset button: /RESET is held while cartridge 5 V and the interface rail stay on and the machine stays in RUN. A flashcart such as a Super EverDrive or FXPAK Pro therefore keeps the game it has loaded; removing power would send it back to its menu. Cartridge power is removed only by SHUTDOWN (request dropped, host reset) or FAULT. The SNES master clock is never changed while running; the region is fixed at power-on (see the [clock plan](clock-plan.md)).

## Verification

The bench uses shortened hold/timeout parameters and rail models that become valid a few clocks after their enable. Every clock it asserts that `bus_permit` is never high with any condition false, never high outside RUN, and that the interface rail is never on without 5 V. Sequence checks: normal bring-up and request drop; a 50-clock soft reset in RUN keeps both rails enabled and the state in RUN while /RESET is held, then releases cleanly; host reset during RUN removes permission on the next clock and shuts down; eFuse fault, over-temperature, configuration loss and 5 V loss each remove permission within one clock, latch with the right code, keep outputs off, refuse `fault_clear` while the run request is still high, and clear properly afterwards; a 5 V rail that never comes up times out with code `0x08`. Result: **PASS**.

Limits: digital behaviour only. The analog veto, eFuse current limit and slew, monitor thresholds and all real timings (reset hold, rail timeouts) must be set from the selected parts and measured on hardware. Hardware inputs are assumed already synchronised; board integration must add synchronisers for asynchronous monitor outputs.

## Cartridge check before 5 V (2026-10-01)

Added for the owner's idea of catching a cartridge that is in back to front; the full description is in [reversed-cartridge-detection.md](reversed-cartridge-detection.md). With `PROBE_ENABLE = 1` (the v2 board) a request first goes through CART CHECK: the [rail monitor](../../fpga/rtl/sn64_rail_monitor.sv) feeds a small test current into the switched-off cartridge rail and reports the rail voltage. A reversed or shorted cartridge holds the rail low. `probe_mode`, taken when the request starts, decides what a failed check does: 0 enforce (fault `0x01`, 5 V never applied), 1 report only (recorded, started anyway), 2 off (no check), 3 check only (recorded, 5 V never applied, pass or fail). The state numbers 0 to 6 are unchanged because other blocks and the menu compare against them; the new states are 7 to 9. /RESET is released during the check, in the sequencer and in `sn64_top`, because its pull-up hangs from the cartridge rail.

`fault_code` bit 0, which was always 0, now means "cartridge check failed in enforce mode". The result of the last check (`probe_done`, `probe_pass`, mode, rail reading) stays readable after the request is dropped and is cleared when the next request starts.

Verification: `tb_power_sequencer` has a second instance with the check and ten more cases (two readings in a row to pass, enforce, report only, check only, off, abort, hardware fault during the check, a monitor that never gives the pin back, and a build without the check asked for check only). `tb_cart_check` runs the sequencer with the real monitor against an ADC model and an electrical model of the rail. Both are in `evaluate.py --mode sim`. Simulation only; the threshold (0.65 V) and the timeout (4 s) are assumptions.

## Power-off order and pins at rest (2026-10-02)

Found by the board-level run ([board-simulation.md](board-simulation.md)): at a start the cartridge's `/RESET` was released about 90 ns before the octets that drive its control pins were switched on, and at power-off `/RESET` and the pins were let go in the same instant. A cartridge's battery RAM is guarded by its `/RESET`; the pins should never be loose while it is high.

- **Pins at rest.** While the cartridge has its 5 V and the sequencer is in IFACE, RUN or SHUTDOWN, the socket owner part ([sn64_header_probe.sv](../../fpga/rtl/sn64_header_probe.sv)) drives the address and strobe octets with every strobe inactive and no clock whenever neither the bridge nor the header read owns them. The data octet stays released. The octet with the CIC clock, the CIC reset and the SNES clock stays driven through SHUTDOWN as well.
- **Hold at power-off.** When the request is dropped, `/RESET` is pulled at once. The rails stay on for `SHUTDOWN_HOLD_MS` with the pins at rest, then the 5 V is switched off and the pins are let go. A fault does not wait: everything goes on the same clock.
- **Level shifter enables.** The byte that brings signals from the socket to the FPGA has its own enable (`snes_sense_oe_n`), on in IFACE, RUN and SHUTDOWN and off otherwise, so that no byte is enabled while its 5 V side has no supply.

Verification: `tb_system` and `tb_game` check on every clock that the socket outputs are never on without cartridge power, are at rest while nobody owns them, and are never released while the cartridge is powered and out of reset; and that `/RESET` has been low for the hold time when the 5 V is switched off. `tb_system` now ends with a power-off. Two fault builds put the old behaviour back (`SN64_FAULT_NO_IDLE_DRIVE`, `SN64_FAULT_NO_SHUTDOWN_HOLD`) and are refused. `tb_header_probe` has a new section for the rest state of the socket owner part. Simulation only.
