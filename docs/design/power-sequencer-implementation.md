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
| RUN (4) | everything on, `bus_permit` may be high | request dropped or host reset → SHUTDOWN |
| SHUTDOWN (5) | reset pulled, rails off | next clock → OFF |
| FAULT (6) | everything off, reset pulled, fault latched | `fault_clear` while `run_request` is low → OFF |

The interface rail is never enabled without cartridge 5 V (translator A side must be powered first; see the power-architecture translator section). `fault_code` records the trip cause: bit 1 configuration loss, 2 host/USB rail, 3 FPGA rails… as coded in the module; bit 3 5 V window, bit 4 interface rail, bit 6 eFuse, bit 7 over-temperature. It is intended for the telemetry registers.

## Verification

The bench uses shortened hold/timeout parameters and rail models that become valid a few clocks after their enable. Every clock it asserts that `bus_permit` is never high with any condition false, never high outside RUN, and that the interface rail is never on without 5 V. Sequence checks: normal bring-up and request drop; host reset during RUN removes permission on the next clock and shuts down; eFuse fault, over-temperature, configuration loss and 5 V loss each remove permission within one clock, latch with the right code, keep outputs off, refuse `fault_clear` while the run request is still high, and clear properly afterwards; a 5 V rail that never comes up times out with code `0x08`. Result: **PASS**.

Limits: digital behaviour only. The analog veto, eFuse current limit and slew, monitor thresholds and all real timings (reset hold, rail timeouts) must be set from the selected parts and measured on hardware. Hardware inputs are assumed already synchronised; board integration must add synchronisers for asynchronous monitor outputs.
